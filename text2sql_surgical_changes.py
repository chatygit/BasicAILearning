"""
text2sql.py — SURGICAL CHANGES (review copy)
=============================================
Only the 3 methods that need edits, de-minified and formatted for review.
Compare each against the live tools/text2sql.py and apply the marked lines only.

Changes in this file:
  A (token win)  tool_query_context   — stop shipping validation_rules to the LLM
  B (token win)  tool_data_context    — stop re-shipping domain_config
  C (bug fix)    tool_query_executor  — null/timestamp-safe serialization (float->int crash)
  D (token/stab) tool_data_context    — cap raw_results_markdown (uncapped payload bomb)

Existing module already imports: json, time, uuid, pandas as pd, and the helpers used below.
No new imports required (json is already imported at the top of text2sql.py).
Each change is wrapped in  # === CHANGE X ... ===  with the ORIGINAL line shown above the NEW line.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional


# =============================================================================
# 1) tool_query_executor  — CHANGE C (null/timestamp-safe serialization)
# =============================================================================
def tool_query_executor(
    domain: str,
    sql_query: str,
    result_headers: str = "",
    columns: str = "",
    user_question: str = "",
    aggregation_columns: str = "",
    conversation_id: str = "",
    soeid: str = "",
    *,
    user_id: str = "",
) -> dict:
    soeid = user_id or get_soeid()
    logger.info("tool_query_executor: resolved user_id=%s", soeid)
    start = time.time()
    config = _get_config(domain)
    try:
        rules_path = config.get_sql_validation_rules_path()
        if rules_path:
            validate_sql_query(sql_query, rules_path)  # server-side re-validation (enforcement point)

        from ..text2sql.utilities.db_adapter import execute_query

        env = config.get_deployment_env()
        db_type = config.get_db_type()
        raw_results = execute_query(sql_query=sql_query, env=env, db_type=db_type)
        if not raw_results:
            return {
                "status": "no_data",
                "message": "Query executed successfully but returned no results.",
                "row_count": 0,
            }

        df = pd.DataFrame(raw_results)
        for calc_fn in config.get_post_query_calculations():
            try:
                df = calc_fn(df, sql_query)
            except Exception as calc_err:
                logger.warning("Post-query calc failed: %s", calc_err)

        execution_key = f"{domain}_{uuid.uuid4().hex[:12]}_{int(time.time())}"

        parsed_columns: Dict[str, Any] = {}
        if columns:
            try:
                parsed_columns = json.loads(columns)
            except json.JSONDecodeError:
                pass

        agg_cols = (
            [c.strip() for c in aggregation_columns.split(",") if c.strip()]
            if aggregation_columns
            else []
        )

        # === CHANGE C (bug fix): null/timestamp-safe rows ==========================
        # df.to_dict("records") leaves raw pd.Timestamp / float NaN objects in the
        # dicts. When the MCP framework serializes the tool return to JSON it crashes
        # with "TypeError: 'float' object cannot be interpreted as an integer" on any
        # result that has a NULL timestamp (e.g. unpriced deals -> NULL PRICING_TS).
        # df.to_json handles NaN/NaT -> null, Timestamp -> ISO, numpy -> native.
        #   ORIGINAL:
        #     store_data = {"rows": df.to_dict("records"), ...}
        #     sample = df.head(5).to_dict("records")
        safe_rows = json.loads(df.to_json(orient="records", date_format="iso"))
        store_data = {
            "rows": safe_rows,  # was: df.to_dict("records")
            "columns": parsed_columns,
            "aggregation_columns": agg_cols,
            "sql_query": sql_query,
            "user_question": user_question,
            "domain": domain,
            "soeid": soeid,
        }
        query_result_store.store(execution_key, store_data)

        sample = safe_rows[:5]  # was: df.head(5).to_dict("records")
        # === END CHANGE C =========================================================

        return {
            "status": "success",
            "execution_key": execution_key,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "sample_data": sample,
        }
    except Exception as e:
        logger.error("Query executor error (domain=%s): %s", domain, e, exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        logger.info("[perf] query_executor(%s): %.2fs", domain, time.time() - start)


# =============================================================================
# 2) tool_query_context  — CHANGE A (do not ship validation_rules to the LLM)
#    NOTE: only the TAIL of this method changes. The large prefetch/context-build
#    body is unchanged and shown compressed as `... (unchanged) ...` so you can
#    focus the diff on the validation_rules load + the return dict.
# =============================================================================
def tool_query_context(
    domain: str,
    user_query: str,
    gfcid: str = "",
    gpnum: str = "",
    client_level: str = "",
    filter_criteria: str = "",
    soeid: str = "",
    platform: str = "desktop",
    *,
    user_id: str = "",
) -> dict:
    soeid = user_id or get_soeid()
    logger.info("tool_query_context: resolved user_id=%s", soeid)
    start = time.time()
    config = _get_config(domain)
    try:
        # ... (unchanged) preflight, entitlement, load_ids, as_of_date prefetch,
        #     schema compaction, filter_criteria formatting, domain_variables build ...
        #     -> produces:  context, full_user_query, effective_client_level,
        #                   load_ids, as_of_date, filter_instruction, domain_variables

        # === CHANGE A (token win): stop returning the full validation_rules array ===
        # The rules array (~5k tokens of regexes) was shipped into the LLM context on
        # every query AND re-sent in history on every subsequent inference (~6x/turn).
        # The executor re-validates server-side (see tool_query_executor), so the model
        # never needs the raw rules — only the instructive error_message on failure.
        #
        # Option 1 (chosen here): drop the load entirely and return an empty list so
        #   the response contract keeps the key.
        # Option 2: return only [r["name"] for r in rules] if any consumer wants names.
        #
        #   ORIGINAL:
        #     rules_path = config.get_sql_validation_rules_path()
        #     validation_rules: List[Dict[str, Any]] = []
        #     if rules_path and os.path.isfile(rules_path):
        #         try:
        #             with open(rules_path, "r") as f:
        #                 rules_yaml = yaml.safe_load(f)
        #                 validation_rules = rules_yaml.get("rules", [])
        #         except Exception as exc:
        #             logger.warning("Failed to load validation rules: %s", exc)
        validation_rules: List[Dict[str, Any]] = []  # not shipped to the LLM; executor enforces
        # === END CHANGE A =========================================================

        return {
            "status": "success",
            "query_context_contract_version": "1.1.0",
            "accepted_input_params": [
                "domain", "user_query", "gfcid", "gpnum",
                "client_level", "filter_criteria", "platform",
            ],
            "domain": domain,
            "schema_context": context,
            "domain_config": domain_variables,
            "user_prompt": user_query,
            "user_query_with_context": full_user_query,
            "entitlement_status": "granted",
            "effective_client_level": effective_client_level or "",
            "load_ids": load_ids,
            "as_of_date": as_of_date or "",
            "filter_instruction": filter_instruction,
            "validation_rules": validation_rules,  # now [] (CHANGE A)
            "gfcid": gfcid,
            "gpnum": gpnum,
            "platform": platform,
        }
    except PermissionError as exc:
        logger.error("Entitlement denied (domain=%s): %s", domain, exc)
        return {"status": "error", "error_type": "entitlement_denied", "message": str(exc)}
    except Exception as e:
        logger.error("Query context error (domain=%s): %s", domain, e, exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        logger.info("[perf] query_context(%s): %.2fs", domain, time.time() - start)


# =============================================================================
# 3) tool_data_context  — CHANGE B (drop duplicate domain_config)
#                         CHANGE D (cap raw_results_markdown)
#    Again only the TAIL changes; the analysis-build body is unchanged.
# =============================================================================
def tool_data_context(
    domain: str,
    execution_key: str,
    user_question: str = "",
    columns: str = "",
    aggregation_columns: str = "",
    as_of_date: str = "",
    client_identifier: str = "",
    client_level: str = "",
    gfcid_name: str = "",
    platform: str = "desktop",
    soeid: str = "",
    *,
    user_id: str = "",
) -> dict:
    soeid = user_id or get_soeid()
    logger.info("tool_data_context: resolved user_id=%s", soeid)
    start = time.time()
    config = _get_config(domain)
    try:
        stored = query_result_store.retrieve(execution_key)
        if not stored:
            return {
                "status": "error",
                "message": f"No data found for execution_key '{execution_key}'. "
                           "Ensure the query_executor tool was called first.",
            }
        rows = stored.get("rows", [])
        if not rows:
            return {"status": "no_data", "message": "The stored result set is empty."}

        df = pd.DataFrame(rows)

        # ... (unchanged) columns_dict / agg_cols_list / question / as_of_date /
        #     numeric_cols / threshold / is_large_dataset / analysis /
        #     business_aggregations / authoritative_facts / display_df /
        #     markdown_table / summary_context / verified_figures ...
        #     -> produces: df, numeric_cols, threshold, is_large_dataset,
        #                  columns_dict, agg_cols_list, question, as_of_date,
        #                  markdown_table, summary_context, verified_figures,
        #                  credit_facility_metrics, display_df, analysis

        # === CHANGE D (token/stability): cap raw_results_markdown =================
        # This was the FULL, uncapped result set rendered as markdown, shipped
        # alongside the already-capped markdown_table. On large results it blows the
        # output-token ceiling (empty response -> "SV_END_OF_MESSAGE"). Cap it to the
        # same display threshold.
        #   ORIGINAL:
        #     raw_results_markdown = _build_raw_results_markdown(df, numeric_cols)
        raw_results_markdown = _build_raw_results_markdown(
            df if not is_large_dataset else df.head(threshold),
            numeric_cols,
        )
        # === END CHANGE D =========================================================

        # === CHANGE B (token win): do NOT re-ship domain_config ===================
        # query_context already returned domain_config this turn; sending it again
        # here duplicates several k tokens in the LLM context. Removed from the
        # return dict. (The two build lines below are now unused and can be deleted.)
        #   ORIGINAL:
        #     domain_variables = config.get_prompt_variables(platform)
        #     domain_variables.update(config.get_text_to_sql_prompt_kwargs())
        #     return { ..., "domain_config": domain_variables, ... }
        # === END CHANGE B =========================================================

        return {
            "status": "success",
            "domain": domain,
            # "domain_config": domain_variables,   # REMOVED (CHANGE B)
            "sql_query": stored.get("sql_query", ""),
            "summary_context": summary_context,
            "markdown_table": markdown_table,
            "raw_results_markdown": raw_results_markdown,  # now capped (CHANGE D)
            "verified_figures": verified_figures,
            "verified_business_metrics": credit_facility_metrics,
            "total_rows": len(df),
            "displayed_rows": len(display_df),
            "numeric_columns": numeric_cols,
            "aggregation_columns": agg_cols_list,
            "as_of_date": as_of_date,
            "is_large_dataset": is_large_dataset,
            "columns": columns_dict,
            "user_question": question,
        }
    except Exception as e:
        logger.error("Data context error (domain=%s): %s", domain, e, exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        logger.info("[perf] data_context(%s): %.2fs", domain, time.time() - start)
