#define DUCKDB_EXTENSION_MAIN

#include "talib_extension.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/function/scalar_function.hpp"
#include "duckdb/main/extension/extension_loader.hpp"
#include "duckdb/parser/parsed_data/create_scalar_function_info.hpp"
#include "duckdb/planner/expression/bound_cast_expression.hpp"
#include "duckdb/planner/expression/bound_function_expression.hpp"

#include <ta_abstract.h>
#include <ta_common.h>
#include <ta_libc.h>

#include <cmath>
#include <cctype>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace duckdb {

namespace {

constexpr idx_t kMaxBars = 10'000'000;

static const struct {
	TA_InputFlags flag;
} kPriceComponents[] = {{TA_IN_PRICE_OPEN},  {TA_IN_PRICE_HIGH}, {TA_IN_PRICE_LOW},
                        {TA_IN_PRICE_CLOSE}, {TA_IN_PRICE_VOLUME}, {TA_IN_PRICE_OPENINTEREST}};

struct TalibScalarFunctionInfo : public ScalarFunctionInfo {
	explicit TalibScalarFunctionInfo(const TA_FuncHandle *handle_p) : handle(handle_p) {
	}
	const TA_FuncHandle *handle;
};

static string SqlNameForTaFunction(const char *ta_name) {
	string s = "ta_";
	for (const char *p = ta_name; *p; p++) {
		s.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(*p))));
	}
	return s;
}

static bool BuildArgTypes(const TA_FuncInfo *fi, vector<LogicalType> &out) {
	out.clear();
	for (unsigned i = 0; i < fi->nbInput; i++) {
		const TA_InputParameterInfo *pi = nullptr;
		if (TA_GetInputParameterInfo(fi->handle, i, &pi) != TA_SUCCESS || !pi) {
			return false;
		}
		switch (pi->type) {
		case TA_Input_Real:
			out.push_back(LogicalType::LIST(LogicalType::DOUBLE));
			break;
		case TA_Input_Integer:
			out.push_back(LogicalType::LIST(LogicalType::INTEGER));
			break;
		case TA_Input_Price:
			for (auto pc : kPriceComponents) {
				if (pi->flags & pc.flag) {
					out.push_back(LogicalType::LIST(LogicalType::DOUBLE));
				}
			}
			break;
		default:
			return false;
		}
	}
	for (unsigned j = 0; j < fi->nbOptInput; j++) {
		const TA_OptInputParameterInfo *oi = nullptr;
		if (TA_GetOptInputParameterInfo(fi->handle, j, &oi) != TA_SUCCESS || !oi) {
			return false;
		}
		switch (oi->type) {
		case TA_OptInput_IntegerRange:
		case TA_OptInput_IntegerList:
			out.push_back(LogicalType::BIGINT);
			break;
		case TA_OptInput_RealRange:
		case TA_OptInput_RealList:
			out.push_back(LogicalType::DOUBLE);
			break;
		default:
			return false;
		}
	}
	return true;
}

static LogicalType BuildReturnType(const TA_FuncInfo *fi) {
	if (fi->nbOutput == 1) {
		const TA_OutputParameterInfo *po = nullptr;
		if (TA_GetOutputParameterInfo(fi->handle, 0, &po) != TA_SUCCESS || !po) {
			return LogicalType::SQLNULL;
		}
		if (po->type == TA_Output_Real) {
			return LogicalType::LIST(LogicalType::DOUBLE);
		}
		if (po->type == TA_Output_Integer) {
			return LogicalType::LIST(LogicalType::INTEGER);
		}
		return LogicalType::SQLNULL;
	}
	child_list_t<LogicalType> children;
	for (unsigned o = 0; o < fi->nbOutput; o++) {
		const TA_OutputParameterInfo *po = nullptr;
		if (TA_GetOutputParameterInfo(fi->handle, o, &po) != TA_SUCCESS || !po) {
			return LogicalType::SQLNULL;
		}
		string fname = po->paramName ? po->paramName : ("out_" + to_string(o));
		if (po->type == TA_Output_Real) {
			children.emplace_back(fname, LogicalType::LIST(LogicalType::DOUBLE));
		} else if (po->type == TA_Output_Integer) {
			children.emplace_back(fname, LogicalType::LIST(LogicalType::INTEGER));
		} else {
			return LogicalType::SQLNULL;
		}
	}
	return LogicalType::STRUCT(std::move(children));
}

static bool ReadDoubleList(const Vector &vec, idx_t chunk_size, idx_t row, vector<double> &out, string &err) {
	UnifiedVectorFormat lv;
	vec.ToUnifiedFormat(chunk_size, lv);
	auto li = lv.sel->get_index(row);
	if (!lv.validity.RowIsValid(li)) {
		err = "NULL list input";
		return false;
	}
	auto lists = UnifiedVectorFormat::GetData<list_entry_t>(lv);
	const auto &entry = lists[li];
	auto &child = ListVector::GetEntry(vec);
	UnifiedVectorFormat cv;
	child.ToUnifiedFormat(ListVector::GetListSize(vec), cv);
	auto cdata = UnifiedVectorFormat::GetData<double>(cv);
	out.resize(entry.length);
	for (idx_t j = 0; j < entry.length; j++) {
		auto ci = cv.sel->get_index(entry.offset + j);
		if (!cv.validity.RowIsValid(ci)) {
			err = "NULL element inside DOUBLE[] input";
			return false;
		}
		out[j] = cdata[ci];
	}
	return true;
}

static bool ReadIntList(const Vector &vec, idx_t chunk_size, idx_t row, vector<int32_t> &out, string &err) {
	UnifiedVectorFormat lv;
	vec.ToUnifiedFormat(chunk_size, lv);
	auto li = lv.sel->get_index(row);
	if (!lv.validity.RowIsValid(li)) {
		err = "NULL list input";
		return false;
	}
	auto lists = UnifiedVectorFormat::GetData<list_entry_t>(lv);
	const auto &entry = lists[li];
	auto &child = ListVector::GetEntry(vec);
	UnifiedVectorFormat cv;
	child.ToUnifiedFormat(ListVector::GetListSize(vec), cv);
	auto cdata = UnifiedVectorFormat::GetData<int32_t>(cv);
	out.resize(entry.length);
	for (idx_t j = 0; j < entry.length; j++) {
		auto ci = cv.sel->get_index(entry.offset + j);
		if (!cv.validity.RowIsValid(ci)) {
			err = "NULL element inside INTEGER[] input";
			return false;
		}
		out[j] = cdata[ci];
	}
	return true;
}

static bool TryReadBigIntArg(const Vector &vec, idx_t chunk_size, idx_t row, int64_t &out) {
	UnifiedVectorFormat v;
	vec.ToUnifiedFormat(chunk_size, v);
	auto vi = v.sel->get_index(row);
	if (!v.validity.RowIsValid(vi)) {
		return false;
	}
	out = UnifiedVectorFormat::GetData<int64_t>(v)[vi];
	return true;
}

static bool TryReadDoubleArg(const Vector &vec, idx_t chunk_size, idx_t row, double &out) {
	UnifiedVectorFormat v;
	vec.ToUnifiedFormat(chunk_size, v);
	auto vi = v.sel->get_index(row);
	if (!v.validity.RowIsValid(vi)) {
		return false;
	}
	out = UnifiedVectorFormat::GetData<double>(v)[vi];
	return true;
}

static void WriteDoubleListRow(Vector &result, idx_t row, idx_t n, const double *src, TA_Integer outBegIdx,
                               TA_Integer outNbElement) {
	D_ASSERT(result.GetType().id() == LogicalTypeId::LIST);
	auto &child = ListVector::GetEntry(result);
	auto child_data = FlatVector::GetData<double>(child);
	auto &child_validity = FlatVector::Validity(child);
	auto lists = FlatVector::GetData<list_entry_t>(result);

	idx_t base_off = 0;
	if (row > 0) {
		const auto &prev = lists[row - 1];
		base_off = prev.offset + prev.length;
	}
	lists[row].offset = base_off;
	lists[row].length = n;
	for (idx_t i = 0; i < n; i++) {
		idx_t p = base_off + i;
		if (i < static_cast<idx_t>(outBegIdx) || i >= static_cast<idx_t>(outBegIdx) + static_cast<idx_t>(outNbElement)) {
			FlatVector::SetNull(child, p, true);
		} else {
			double v = src[i - static_cast<idx_t>(outBegIdx)];
			if (std::isnan(v)) {
				FlatVector::SetNull(child, p, true);
			} else {
				child_validity.SetValid(p);
				child_data[p] = v;
			}
		}
	}
}

static void WriteIntListRow(Vector &result, idx_t row, idx_t n, const TA_Integer *src, TA_Integer outBegIdx,
                            TA_Integer outNbElement) {
	D_ASSERT(result.GetType().id() == LogicalTypeId::LIST);
	auto &child = ListVector::GetEntry(result);
	auto child_data = FlatVector::GetData<int32_t>(child);
	auto &child_validity = FlatVector::Validity(child);
	auto lists = FlatVector::GetData<list_entry_t>(result);

	idx_t base_off = 0;
	if (row > 0) {
		const auto &prev = lists[row - 1];
		base_off = prev.offset + prev.length;
	}
	lists[row].offset = base_off;
	lists[row].length = n;
	for (idx_t i = 0; i < n; i++) {
		idx_t p = base_off + i;
		if (i < static_cast<idx_t>(outBegIdx) || i >= static_cast<idx_t>(outBegIdx) + static_cast<idx_t>(outNbElement)) {
			FlatVector::SetNull(child, p, true);
		} else {
			child_validity.SetValid(p);
			child_data[p] = src[i - static_cast<idx_t>(outBegIdx)];
		}
	}
}

static void TalibScalarBind(ClientContext &context, ScalarFunction &bound_function,
                            vector<unique_ptr<Expression>> &arguments) {
	for (auto &arg : arguments) {
		if (arg->return_type.id() == LogicalTypeId::ARRAY) {
			arg = BoundCastExpression::AddArrayCastToList(context, std::move(arg));
		}
	}
}

static unique_ptr<FunctionData> TalibScalarBindData(ClientContext &context, ScalarFunction &bound_function,
                                                    vector<unique_ptr<Expression>> &arguments) {
	TalibScalarBind(context, bound_function, arguments);
	return nullptr;
}

static void TalibScalarExec(DataChunk &args, ExpressionState &state, Vector &result) {
	auto &func_expr = state.expr.Cast<BoundFunctionExpression>();
	auto &fn = func_expr.function;
	D_ASSERT(fn.function_info);
	auto &tinfo = fn.function_info->Cast<TalibScalarFunctionInfo>();
	const TA_FuncHandle *handle = tinfo.handle;

	const TA_FuncInfo *fi = nullptr;
	if (TA_GetFuncInfo(handle, &fi) != TA_SUCCESS || !fi) {
		throw InternalException("talib: missing TA_FuncInfo");
	}

	const idx_t count = args.size();
	string err;

	// Total elements in list child vectors (sum of list lengths per row).
	idx_t total_double_child = 0;
	for (idx_t r = 0; r < count; r++) {
		bool row_ok = true;
		idx_t arg_col = 0;
		idx_t n = 0;
		for (unsigned in_idx = 0; in_idx < fi->nbInput; in_idx++) {
			const TA_InputParameterInfo *pi = nullptr;
			TA_GetInputParameterInfo(handle, in_idx, &pi);
			switch (pi->type) {
			case TA_Input_Real: {
				vector<double> tmp;
				if (!ReadDoubleList(args.data[arg_col++], count, r, tmp, err)) {
					row_ok = false;
				} else if (n == 0) {
					n = tmp.size();
				} else if (tmp.size() != n) {
					err = "TA-Lib inputs must have equal length";
					row_ok = false;
				}
				break;
			}
			case TA_Input_Integer: {
				vector<int32_t> tmp;
				if (!ReadIntList(args.data[arg_col++], count, r, tmp, err)) {
					row_ok = false;
				} else if (n == 0) {
					n = tmp.size();
				} else if (tmp.size() != n) {
					err = "TA-Lib inputs must have equal length";
					row_ok = false;
				}
				break;
			}
			case TA_Input_Price: {
				for (auto pc : kPriceComponents) {
					if (pi->flags & pc.flag) {
						vector<double> tmp;
						if (!ReadDoubleList(args.data[arg_col++], count, r, tmp, err)) {
							row_ok = false;
						} else if (n == 0) {
							n = tmp.size();
						} else if (tmp.size() != n) {
							err = "TA-Lib inputs must have equal length";
							row_ok = false;
						}
					}
				}
				break;
			}
			default:
				row_ok = false;
				err = "Unsupported TA input type";
				break;
			}
			if (!row_ok) {
				break;
			}
		}
		if (row_ok && n > kMaxBars) {
			row_ok = false;
			err = "TA-Lib input exceeds max bar count";
		}
		if (row_ok) {
			total_double_child += n;
		}
	}

	result.SetVectorType(VectorType::FLAT_VECTOR);
	if (fi->nbOutput == 1) {
		ListVector::Reserve(result, total_double_child);
	} else {
		auto &entries = StructVector::GetEntries(result);
		for (auto &e : entries) {
			ListVector::Reserve(*e, total_double_child);
		}
	}

	auto &res_validity = FlatVector::Validity(result);
	res_validity.SetAllValid(count);

	for (idx_t r = 0; r < count; r++) {
		TA_ParamHolder *holder = nullptr;
		if (TA_ParamHolderAlloc(handle, &holder) != TA_SUCCESS) {
			throw InvalidInputException("talib: TA_ParamHolderAlloc failed");
		}

		vector<vector<double>> real_storage(fi->nbInput);
		vector<vector<int32_t>> int_storage(fi->nbInput);
		idx_t arg_col = 0;
		idx_t n = 0;
		bool row_ok = true;

		auto fail_row = [&](const string &e) {
			err = e;
			row_ok = false;
		};

		for (unsigned in_idx = 0; in_idx < fi->nbInput; in_idx++) {
			const TA_InputParameterInfo *pi = nullptr;
			TA_GetInputParameterInfo(handle, in_idx, &pi);
			switch (pi->type) {
			case TA_Input_Real: {
				if (!ReadDoubleList(args.data[arg_col], count, r, real_storage[in_idx], err)) {
					row_ok = false;
					break;
				}
				arg_col++;
				if (n == 0) {
					n = real_storage[in_idx].size();
				} else if (real_storage[in_idx].size() != n) {
					fail_row("TA-Lib inputs must have equal length");
					break;
				}
				if (TA_SetInputParamRealPtr(holder, in_idx, real_storage[in_idx].data()) != TA_SUCCESS) {
					fail_row("TA_SetInputParamRealPtr failed");
				}
				break;
			}
			case TA_Input_Integer: {
				if (!ReadIntList(args.data[arg_col], count, r, int_storage[in_idx], err)) {
					row_ok = false;
					break;
				}
				arg_col++;
				if (n == 0) {
					n = int_storage[in_idx].size();
				} else if (int_storage[in_idx].size() != n) {
					fail_row("TA-Lib inputs must have equal length");
					break;
				}
				if (TA_SetInputParamIntegerPtr(holder, in_idx, int_storage[in_idx].data()) != TA_SUCCESS) {
					fail_row("TA_SetInputParamIntegerPtr failed");
				}
				break;
			}
			case TA_Input_Price: {
				const double *po = nullptr;
				const double *ph = nullptr;
				const double *pl = nullptr;
				const double *pco = nullptr;
				const double *pv = nullptr;
				const double *poi = nullptr;
				vector<vector<double>> price_vecs;
				for (auto pc : kPriceComponents) {
					if (pi->flags & pc.flag) {
						vector<double> tmp;
						if (!ReadDoubleList(args.data[arg_col], count, r, tmp, err)) {
							row_ok = false;
							break;
						}
						arg_col++;
						if (n == 0) {
							n = tmp.size();
						} else if (tmp.size() != n) {
							fail_row("TA-Lib inputs must have equal length");
							break;
						}
						price_vecs.push_back(std::move(tmp));
						double *base = price_vecs.back().data();
						if (pc.flag == TA_IN_PRICE_OPEN) {
							po = base;
						} else if (pc.flag == TA_IN_PRICE_HIGH) {
							ph = base;
						} else if (pc.flag == TA_IN_PRICE_LOW) {
							pl = base;
						} else if (pc.flag == TA_IN_PRICE_CLOSE) {
							pco = base;
						} else if (pc.flag == TA_IN_PRICE_VOLUME) {
							pv = base;
						} else if (pc.flag == TA_IN_PRICE_OPENINTEREST) {
							poi = base;
						}
					}
				}
				if (!row_ok) {
					break;
				}
				if (TA_SetInputParamPricePtr(holder, in_idx, po, ph, pl, pco, pv, poi) != TA_SUCCESS) {
					fail_row("TA_SetInputParamPricePtr failed");
				}
				break;
			}
			default:
				fail_row("Unsupported TA input type");
				break;
			}
		}

		for (unsigned oj = 0; row_ok && oj < fi->nbOptInput; oj++) {
			const TA_OptInputParameterInfo *oi = nullptr;
			TA_GetOptInputParameterInfo(handle, oj, &oi);
			Vector &avec = args.data[arg_col++];
			switch (oi->type) {
			case TA_OptInput_IntegerRange:
			case TA_OptInput_IntegerList: {
				int64_t iv = 0;
				if (!TryReadBigIntArg(avec, count, r, iv)) {
					fail_row("NULL optional integer parameter");
					break;
				}
				if (iv > std::numeric_limits<int>::max() || iv < std::numeric_limits<int>::min()) {
					fail_row("Optional integer parameter out of range for TA-Lib");
					break;
				}
				if (TA_SetOptInputParamInteger(holder, oj, static_cast<TA_Integer>(iv)) != TA_SUCCESS) {
					fail_row("TA_SetOptInputParamInteger failed");
				}
				break;
			}
			case TA_OptInput_RealRange:
			case TA_OptInput_RealList: {
				double dv = 0;
				if (!TryReadDoubleArg(avec, count, r, dv)) {
					fail_row("NULL optional floating parameter");
					break;
				}
				if (TA_SetOptInputParamReal(holder, oj, dv) != TA_SUCCESS) {
					fail_row("TA_SetOptInputParamReal failed");
				}
				break;
			}
			default:
				fail_row("Unsupported optional TA parameter type");
				break;
			}
		}

		if (!row_ok || n == 0) {
			TA_ParamHolderFree(holder);
			res_validity.SetInvalid(r);
			continue;
		}
		if (n > kMaxBars) {
			TA_ParamHolderFree(holder);
			res_validity.SetInvalid(r);
			continue;
		}

		vector<vector<double>> out_real(fi->nbOutput);
		vector<vector<TA_Integer>> out_int(fi->nbOutput);
		for (unsigned o = 0; o < fi->nbOutput; o++) {
			const TA_OutputParameterInfo *po = nullptr;
			TA_GetOutputParameterInfo(handle, o, &po);
			if (po->type == TA_Output_Real) {
				out_real[o].resize(n);
				if (TA_SetOutputParamRealPtr(holder, o, out_real[o].data()) != TA_SUCCESS) {
					TA_ParamHolderFree(holder);
					res_validity.SetInvalid(r);
					row_ok = false;
					break;
				}
			} else if (po->type == TA_Output_Integer) {
				out_int[o].resize(n);
				if (TA_SetOutputParamIntegerPtr(holder, o, out_int[o].data()) != TA_SUCCESS) {
					TA_ParamHolderFree(holder);
					res_validity.SetInvalid(r);
					row_ok = false;
					break;
				}
			}
		}

		TA_Integer outBeg = 0;
		TA_Integer outNb = 0;
		TA_RetCode rc = TA_CallFunc(holder, 0, static_cast<TA_Integer>(n) - 1, &outBeg, &outNb);
		TA_ParamHolderFree(holder);

		if (rc != TA_SUCCESS) {
			res_validity.SetInvalid(r);
			continue;
		}

		if (fi->nbOutput == 1) {
			const TA_OutputParameterInfo *po0 = nullptr;
			TA_GetOutputParameterInfo(handle, 0, &po0);
			if (po0->type == TA_Output_Real) {
				WriteDoubleListRow(result, r, n, out_real[0].data(), outBeg, outNb);
			} else {
				WriteIntListRow(result, r, n, out_int[0].data(), outBeg, outNb);
			}
		} else {
			auto &centries = StructVector::GetEntries(result);
			for (unsigned o = 0; o < fi->nbOutput; o++) {
				const TA_OutputParameterInfo *po = nullptr;
				TA_GetOutputParameterInfo(handle, o, &po);
				if (po->type == TA_Output_Real) {
					WriteDoubleListRow(*centries[o], r, n, out_real[o].data(), outBeg, outNb);
				} else {
					WriteIntListRow(*centries[o], r, n, out_int[o].data(), outBeg, outNb);
				}
			}
		}
	}

	if (fi->nbOutput == 1) {
		idx_t off = 0;
		auto lists = FlatVector::GetData<list_entry_t>(result);
		for (idx_t r = 0; r < count; r++) {
			if (!res_validity.RowIsValid(r)) {
				continue;
			}
			off += lists[r].length;
		}
		ListVector::SetListSize(result, off);
	} else {
		auto &centries = StructVector::GetEntries(result);
		idx_t max_off = 0;
		auto lists = FlatVector::GetData<list_entry_t>(*centries[0]);
		for (idx_t r = 0; r < count; r++) {
			if (!res_validity.RowIsValid(r)) {
				continue;
			}
			max_off = MaxValue(max_off, lists[r].offset + lists[r].length);
		}
		for (auto &c : centries) {
			ListVector::SetListSize(*c, max_off);
		}
		for (idx_t r = 0; r < count; r++) {
			if (res_validity.RowIsValid(r)) {
				continue;
			}
			for (auto &c : centries) {
				auto le = FlatVector::GetData<list_entry_t>(*c);
				le[r].offset = 0;
				le[r].length = 0;
			}
		}
	}

	if (fi->nbOutput == 1 && result.GetType().id() == LogicalTypeId::LIST) {
		auto le = FlatVector::GetData<list_entry_t>(result);
		for (idx_t r = 0; r < count; r++) {
			if (!res_validity.RowIsValid(r)) {
				le[r].offset = 0;
				le[r].length = 0;
			}
		}
	}

	result.Verify(count);
}

static void RegisterTalibFromFuncInfo(ExtensionLoader &loader, const TA_FuncInfo *fi) {
	vector<LogicalType> arg_types;
	if (!BuildArgTypes(fi, arg_types)) {
		return;
	}
	LogicalType ret = BuildReturnType(fi);
	if (ret.id() == LogicalTypeId::SQLNULL) {
		return;
	}
	ScalarFunction fn(SqlNameForTaFunction(fi->name), std::move(arg_types), std::move(ret), TalibScalarExec,
	                  TalibScalarBindData);
	fn.function_info = make_shared_ptr<TalibScalarFunctionInfo>(fi->handle);
	fn.null_handling = FunctionNullHandling::SPECIAL_HANDLING;
	loader.RegisterFunction(fn);
}

struct ForeachCtx {
	ExtensionLoader *loader = nullptr;
	idx_t *registered = nullptr;
};

static void ForeachRegister(const TA_FuncInfo *fi, void *opaque) {
	auto *ctx = static_cast<ForeachCtx *>(opaque);
	try {
		RegisterTalibFromFuncInfo(*ctx->loader, fi);
		(*ctx->registered)++;
	} catch (const std::exception &) {
		/* Skip functions with unsupported signatures or registration clashes. */
	}
}

} // namespace

static void LoadInternal(ExtensionLoader &loader) {
	static std::once_flag ta_init;
	std::call_once(ta_init, [] {
		if (TA_Initialize() != TA_SUCCESS) {
			throw IOException("TA_Initialize failed");
		}
	});
	idx_t registered = 0;
	ForeachCtx ctx {&loader, &registered};
	TA_ForEachFunc(ForeachRegister, &ctx);
	if (registered == 0) {
		throw IOException("talib extension: no TA-Lib functions were registered");
	}
}

void TalibExtension::Load(ExtensionLoader &loader) {
	LoadInternal(loader);
}

std::string TalibExtension::Name() {
	return "talib";
}

std::string TalibExtension::Version() const {
#ifdef EXT_VERSION_TALIB
	return EXT_VERSION_TALIB;
#else
	return "";
#endif
}

} // namespace duckdb

extern "C" {

DUCKDB_CPP_EXTENSION_ENTRY(talib, loader) {
	duckdb::LoadInternal(loader);
}
}
