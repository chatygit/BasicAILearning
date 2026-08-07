"""VERBATIM transcription of the CURRENT server tool_query_executor
(shared by bk42867 via screenshots, 2026-07-29). This replaces the outdated
text2sql.py as the diff baseline. Notes:
  - sample = safe_rows[:20] ALREADY present (F1 core applied)
  - CHANGE C (safe serialization) present
  - CHANGE E (entitlement) ABSENT - slot marked below
"""

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
    # Resolve SOEID: prefer explicit user_id kwarg from the MCP server
    # wrapper, then fall back to the SoeidAuth middleware ContextVar.
    soeid = user_id or get_soeid()
    logger.info("tool_query_executor: resolved user_id=%s", soeid)
    start = time.time()
    config = _get_config(domain)

    try:
        # Validate SQL before execution
        rules_path = config.get_sql_validation_rules_path()
        if rules_path:
            validate_sql_query(sql_query, rules_path)

        # <<< CHANGE E SLOT: entitlement pre_execute hook goes HERE >>>

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

        # Apply post-query calculations
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

        safe_rows = json.loads(df.to_json(orient="records", date_format="iso"))

        store_data = {
            "rows": safe_rows,
            "columns": parsed_columns,
            "aggregation_columns": agg_cols,
            "sql_query": sql_query,
            "user_question": user_question,
            "domain": domain,
            "soeid": soeid,
        }
        query_result_store.store(execution_key, store_data)

        sample = safe_rows[:20]  # <<< PATCH 1 replaces this line >>>

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
