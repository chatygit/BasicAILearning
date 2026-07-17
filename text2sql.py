import copy,datetime,json,logging,os,time,uuid;from concurrent.futures import ThreadPoolExecutor;from concurrent.futures import TimeoutError as FuturesTimeoutError;from typing import Any,Dict,List,Optional;import pandas as pd,yaml;from ..auth import get_soeid;from ..text2sql.domain_registry import get_domain_config;from ..text2sql.utilities.business_aggregations import BusinessAggregationEngine;from ..text2sql.utilities.data_analyzer import DataAnalyzer;from ..text2sql.utilities.markdown_utils import format_dataframe_to_markdown;from ..text2sql.utilities.query_result_store import query_result_store;from ..text2sql.utilities.validate_sql_query import validate_sql_query;from ..credit_facility_metrics import build_credit_facility_verified_section as _build_credit_facility_verified_section;from ..text2sql_context_helpers import _apply_prompt_variable_overrides,_check_entitlement,_format_filter_criteria_for_prompt,_initialize_as_of_date_for_domain,_initialize_load_ids_for_domain,_run_query_context_preflight,_upsert_filter_criteria_value;from ..text2sql_data_context_helpers import _build_authoritative_facts,_build_compact_analysis_context,_build_raw_results_markdown,_build_summary_context,_identify_numeric_columns,_normalize_aggregation_columns,_normalize_column_metadata,_select_display_columns,_format_authoritative_facts_for_summary;from ..text2sql_entity_helpers import _build_entity_selection_token,_build_entity_snapshot,_execute_sql_entity_search,_extract_resolution_metadata,_infer_entity_snapshot_source,_resolve_named_entity_search_template,_sanitize_sql_input
logger=logging.getLogger(__name__)
def _get_config(domain:str):return get_domain_config(domain)
def _build_fuzzy_fallback_hint(domain:str,entity_name:str,column_name:str="COMPANY_NAME")->Dict[str,Any]:
 if not entity_name:return{}
 try:
  cfg=_get_config(domain)
  fuzzy_cfg=cfg.get_fuzzy_config()
 except Exception:fuzzy_cfg=None
 if not fuzzy_cfg:return{}
 cols=fuzzy_cfg.get("columns")or[]
 if cols and column_name not in cols:column_name="COMPANY_NAME"if"COMPANY_NAME"in cols else str(cols[0])
 return{"next_action":"call_fuzzy_resolve","suggested_tool":{"name":"text2sql_fuzzy_resolve","args":{"domain":domain,"column_name":column_name,"fuzzy_input":entity_name},"reason":f"Exact SQL match returned no rows. Try vector-similarity resolution against {column_name} before telling the user nothing was found."}}
def _sql_escape(value:str)->str:return(value or"").replace("'","''")
def _extract_fuzzy_match_value(match:Any)->str:
 if isinstance(match,str):return match.strip()
 if not isinstance(match,dict):return""
 for key in("value","column_value","matched_value","candidate","text","company_name","name"):
  value=match.get(key)
  if isinstance(value,str)and value.strip():return value.strip()
 return""
def _extract_fuzzy_match_gfcid(match:Any)->str:
 if not isinstance(match,dict):return""
 for key in("gfcid","GFCID"):
  value=match.get(key)
  if value is None:continue
  text=str(value).strip()
  if text:return text
 return""
def _filter_non_gsg_credit_facility_fuzzy_matches(matches:List[Any],soeid:str,column_name:str,env:str,db_type:str)->tuple[List[Any],List[str]]:
 from ..text2sql.utilities.db_adapter import execute_query
 normalized_soeid=(soeid or"").strip().upper()
 if not normalized_soeid:return[],[]
 normalized_column=(column_name or"").strip().upper()
 if normalized_column!="COMPANY_NAME":return matches,[]
 def _row_value(row:Any,key:str,index:int)->str:
  if isinstance(row,dict):
   value=row.get(key)
   if value is None and key.upper()!=key:value=row.get(key.upper())
   return""if value is None else str(value).strip()
  if isinstance(row,(list,tuple))and len(row)>index:return""if row[index]is None else str(row[index]).strip()
  return""
 candidate_gfcids=sorted({_extract_fuzzy_match_gfcid(match)for match in matches if _extract_fuzzy_match_gfcid(match)})
 entitled_gfcids:set[str]=set()
 if candidate_gfcids:
  in_clause=",".join(f"'{_sql_escape(gfcid)}'" for gfcid in candidate_gfcids)
  gfcid_query=f"SELECT DISTINCT f.gfcid FROM DGLOBE.CREDIT_FACILITY_ENTITLEMENT_VW f WHERE f.has_exposure = 'Y' AND UPPER(f.soeid) = '{_sql_escape(normalized_soeid)}' AND f.gfcid IN ({in_clause})"
  rows=execute_query(sql_query=gfcid_query,env=env,db_type=db_type)
  entitled_gfcids={_row_value(row,"GFCID",0)for row in(rows or[])if _row_value(row,"GFCID",0)}
 values_without_gfcid=sorted({_extract_fuzzy_match_value(match).upper()for match in matches if _extract_fuzzy_match_value(match)and not _extract_fuzzy_match_gfcid(match)})
 company_to_gfcids:Dict[str,set[str]]={}
 if values_without_gfcid:
  in_clause=",".join(f"'{_sql_escape(value)}'" for value in values_without_gfcid)
  name_query=f"SELECT DISTINCT UPPER(t.company_name) AS company_name, t.gfcid FROM dglobe.bda_credit_facility_name_mv t INNER JOIN DGLOBE.CREDIT_FACILITY_ENTITLEMENT_VW e ON t.gfcid = e.gfcid AND t.cagid = e.cagid WHERE e.has_exposure = 'Y' AND UPPER(e.soeid) = '{_sql_escape(normalized_soeid)}' AND UPPER(t.company_name) IN ({in_clause})"
  rows=execute_query(sql_query=name_query,env=env,db_type=db_type)
  for row in rows or[]:
   company_name=_row_value(row,"COMPANY_NAME",0).upper()
   gfcid=_row_value(row,"GFCID",1)
   if not company_name or not gfcid:continue
   company_to_gfcids.setdefault(company_name,set()).add(gfcid)
   entitled_gfcids.add(gfcid)
 filtered:List[Any]=[]
 for match in matches:
  gfcid=_extract_fuzzy_match_gfcid(match)
  if gfcid:
   if gfcid in entitled_gfcids:filtered.append(match)
   continue
  company_name=_extract_fuzzy_match_value(match).upper()
  if company_name in company_to_gfcids:filtered.append(match)
 return filtered,sorted(entitled_gfcids)
def tool_entity_search(domain:str,entity_name:str="",gfcid:str="",cagid:str="",entity_type:str="",soeid:str="",deal_id:str="",*,user_id:str="")->dict:
 soeid=user_id or get_soeid()
 logger.info("tool_entity_search: resolved user_id=%s",soeid)
 start=time.time()
 config=_get_config(domain)
 if deal_id and not entity_type:entity_type="deal_name"
 try:
  if domain=="credit_facility":return _credit_facility_entity_search(config,entity_name=entity_name,gfcid=gfcid,cagid=cagid,soeid=soeid)
  search_mode=config.get_entity_search_mode()
  if search_mode=="api":results=_execute_api_entity_search(config,entity_name=entity_name,gfcid=gfcid,soeid=soeid)
  else:results=_execute_sql_entity_search(config,entity_name=entity_name,gfcid=gfcid,cagid=cagid,entity_type=entity_type,deal_id=deal_id)
  if not results:
   response={"status":"no_results","message":f"No results found for the given search criteria in {domain}.","entity_type":"unknown","resolved_identifier_type":"","resolved_identifier_value":"","resolved_name":"","user_confirmation_required":"no","confidence":"high"}
   if entity_name and not(gfcid or cagid or deal_id):
    hint=_build_fuzzy_fallback_hint(domain,entity_name)
    if hint:
     response.update(hint)
     response["message"]+=" Try `text2sql_fuzzy_resolve` for approximate matches."
   return response
  filter_proc=config.get_entity_filter_processor()
  if filter_proc:results=filter_proc(results)
  if len(results)>1:return{"status":"ambiguous","legacy_status":"disambiguation","message":"Multiple matches found. Please select one.","results":results,"count":len(results),"entity_type":(entity_type or"unknown").replace("_name",""),"resolved_identifier_type":"","resolved_identifier_value":"","resolved_name":"","user_confirmation_required":"yes","confidence":"high"}
  entity=results[0]
  resolution=_extract_resolution_metadata(entity,entity_type_hint=entity_type)
  if resolution.get("missing_preferred_identifier"):
   preferred_type=resolution.get("preferred_identifier_type","identifier")
   return{"status":"ambiguous","legacy_status":"disambiguation","message":f"I found a close match but could not resolve the expected {preferred_type} for this {resolution.get('entity_type','entity')} intent. Please choose a row with a concrete identifier.","results":results,"count":len(results),"entity_type":resolution.get("entity_type","unknown"),"resolved_identifier_type":"","resolved_identifier_value":"","resolved_name":resolution.get("resolved_name",""),"user_confirmation_required":"yes","confidence":resolution.get("confidence","medium")}
  entity_snapshot=_build_entity_snapshot(entity,config.get_entity_context_mapping())
  selection_token=_build_entity_selection_token(entity_snapshot,resolution)
  return{"status":"success","entity":entity,"resolution":resolution,"entity_type":resolution.get("entity_type","unknown"),"resolved_name":resolution.get("resolved_name",""),"resolved_identifier_type":resolution.get("resolved_identifier_type",""),"resolved_identifier_value":resolution.get("resolved_identifier_value",""),"user_confirmation_required":"yes"if resolution.get("user_confirmation_required")else"no","confidence":resolution.get("confidence","high"),"selection_token":selection_token,"entity_snapshot":entity_snapshot,"snapshot_fields_source":_infer_entity_snapshot_source(entity_snapshot),"requires_follow_up":False,"next_action":{"name":"text2sql_query_context","reason":"Entity is resolved. Continue to query_context/query generation using resolution.filter_criteria without extra confirmation.","suggested_args":{"gfcid":resolution["resolved_identifier_value"]if resolution["resolved_identifier_type"]=="GFCID"else"","gpnum":resolution["resolved_identifier_value"]if resolution["resolved_identifier_type"]=="GPNUM"else"","filter_criteria":resolution.get("filter_criteria",{})}}}
 except Exception as e:
  logger.error("Entity search error (domain=%s): %s",domain,e,exc_info=True)
  return{"status":"error","message":str(e)}
 finally:logger.info("[perf] entity_search(%s): %.2fs",domain,time.time()-start)
def _execute_api_entity_search(config,entity_name:str="",gfcid:str="",soeid:str="")->list:
 from ..text2sql.utilities.api_client import api_entity_search
 api_config=config.get_api_config()
 if not api_config:raise ValueError(f"API config not set for domain '{config.get_domain_name()}'")
 raw_results=api_entity_search(api_config,entity_name=entity_name,gfcid=gfcid,soeid=soeid)
 mapper=config.get_entity_search_result_mapper()
 return mapper(raw_results)if raw_results else[]
def _credit_facility_entity_search(config,entity_name:str="",gfcid:str="",cagid:str="",soeid:str="")->dict:
 from ..text2sql.domains.credit_facility.components import determine_user_persona
 env=config.get_deployment_env()
 db_type=config.get_db_type()
 effective_soeid=soeid or get_soeid()
 persona=determine_user_persona(effective_soeid)
 logger.info("credit_facility entity_search: soeid=%s, persona=%s",effective_soeid,persona)
 if cagid:return _cf_search_by_cagid(cagid,persona,effective_soeid,env,db_type)
 if gfcid:return _cf_search_by_gfcid(gfcid,persona,effective_soeid,env,db_type)
 if entity_name:return _cf_search_by_name(entity_name,persona,effective_soeid,env,db_type)
 return{"status":"error","message":"No search criteria provided."}
def _cf_search_by_cagid(cagid:str,persona:str,soeid:str,env:str,db_type:str)->dict:
 from ..text2sql.domains.credit_facility.components import build_filter_criteria,check_entitlement,format_no_results_error,format_permission_denied_error
 from ..text2sql.domains.credit_facility.components.query_builder import build_cagid_query
 from ..text2sql.utilities.db_adapter import execute_query
 query=build_cagid_query(cagid,persona)
 result=execute_query(sql_query=query,env=env,db_type=db_type)
 if not result:return{"status":"no_results","message":format_no_results_error(cagid,"CAGID"),"user_persona":persona}
 first_row=result[0]
 if isinstance(first_row,dict):client_level=first_row.get("CLIENT_LEVEL")or next(iter(first_row.values()))
 else:client_level=first_row[0]
 entitled,ent_level=check_entitlement(soeid,persona,gfcid="",cagid=cagid,env=env)
 if not entitled:
  logger.warning("credit_facility: permission_denied for soeid=%s persona=%s cagid=%s",soeid,persona,cagid)
  return{"status":"permission_denied","message":format_permission_denied_error(cagid),"user_persona":persona,"soeid":soeid}
 return{"status":"success","entity":{"cagid":cagid,"client_level":ent_level or client_level},"filter_criteria":build_filter_criteria(cagid=cagid),"user_persona":persona,"soeid":soeid}
def _cf_search_by_gfcid(gfcid:str,persona:str,soeid:str,env:str,db_type:str)->dict:
 from ..text2sql.domains.credit_facility.components import build_filter_criteria,check_entitlement,format_disambiguation_table,format_no_results_error,format_permission_denied_error,get_entitled_cagids
 from ..text2sql.domains.credit_facility.components.query_builder import build_gfcid_query
 from ..text2sql.utilities.db_adapter import execute_query
 query=build_gfcid_query(gfcid,persona)
 raw=execute_query(sql_query=query,env=env,db_type=db_type)
 if not raw:return{"status":"no_results","message":format_no_results_error(gfcid,"GFCID"),"user_persona":persona}
 entities=[{"cagid":r["CAGID"]if isinstance(r,dict)else r[0],"cagid_name":r["CAGID_NAME"]if isinstance(r,dict)else r[1],"client_level":r["CLIENT_LEVEL"]if isinstance(r,dict)else r[2],"gfcid":r["GFCID"]if isinstance(r,dict)else r[3],"gfcid_name":r["GFCID_NAME"]if isinstance(r,dict)else r[4]}for r in raw]
 entitled,ent_level=check_entitlement(soeid,persona,gfcid=gfcid,env=env)
 if not entitled:
  display_name=entities[0].get("gfcid_name",gfcid)
  logger.warning("credit_facility: permission_denied for soeid=%s persona=%s gfcid=%s",soeid,persona,gfcid)
  return{"status":"permission_denied","message":format_permission_denied_error(display_name),"user_persona":persona,"soeid":soeid}
 if persona=="NON_GSG" and len(entities)>1:
  entitled_cagids=get_entitled_cagids(soeid,gfcid,env=env)
  filtered=[e for e in entities if str(e.get("cagid",""))in entitled_cagids]
  if not filtered:
   display_name=entities[0].get("gfcid_name",gfcid)
   logger.warning("credit_facility: NON_GSG user soeid=%s passed GFCID entitlement for gfcid=%s but has no entitled CAGIDs in disambiguation set.",soeid,gfcid)
   return{"status":"permission_denied","message":format_permission_denied_error(display_name),"user_persona":persona,"soeid":soeid}
  entities=filtered
 if len(entities)>1:
  table=format_disambiguation_table(entities,"cagid",gfcid=gfcid)
  return{"status":"disambiguation","message":table,"results":entities,"count":len(entities),"user_persona":persona,"soeid":soeid}
 entity=entities[0]
 client_level=ent_level or entity.get("client_level","")
 has_multiple_cagids=False
 return{"status":"success","entity":{**entity,"client_level":client_level},"filter_criteria":build_filter_criteria(gfcid=gfcid,cagid=entity.get("cagid"),has_multiple_cagids=has_multiple_cagids),"user_persona":persona,"soeid":soeid}
def _cf_search_by_name(entity_name:str,persona:str,soeid:str,env:str,db_type:str)->dict:
 from ..text2sql.domains.credit_facility.components import build_filter_criteria,format_disambiguation_table,format_no_results_error
 from ..text2sql.domains.credit_facility.components.query_builder import build_name_search_query
 from ..text2sql.utilities.db_adapter import execute_query
 pattern=entity_name.upper().replace("'","''")
 query=build_name_search_query(pattern,entity_name,persona,soeid=soeid)
 raw=execute_query(sql_query=query,env=env,db_type=db_type)
 if not raw:
  response={"status":"no_results","message":format_no_results_error(entity_name,"company"),"user_persona":persona,"soeid":soeid}
  hint=_build_fuzzy_fallback_hint("credit_facility",entity_name,column_name="COMPANY_NAME")
  if hint:
   response.update(hint)
   response["message"]+=f"\n\n_Tip: try `text2sql_fuzzy_resolve` with `column_name=\"COMPANY_NAME\"` and `fuzzy_input=\"{entity_name}\"` to look for approximate matches._"
  return response
 entities=[{"gfcid":r["GFCID"]if isinstance(r,dict)else r[3],"gfcid_name":r["GFCID_NAME"]if isinstance(r,dict)else r[4],"client_level":r["CLIENT_LEVEL"]if isinstance(r,dict)else r[2],"cagid":r["CAGID"]if isinstance(r,dict)else r[0],"cagid_name":r["CAGID_NAME"]if isinstance(r,dict)else r[1]}for r in raw]
 if len(entities)>=1:
  table=format_disambiguation_table(entities,"gfcid")
  return{"status":"disambiguation","message":table,"results":entities,"count":len(entities),"user_persona":persona,"soeid":soeid}
 entity=entities[0]
 return{"status":"success","entity":entity,"filter_criteria":build_filter_criteria(gfcid=entity.get("gfcid"),cagid=entity.get("cagid"),has_multiple_cagids=False),"user_persona":persona,"soeid":soeid}
def tool_query_executor(domain:str,sql_query:str,result_headers:str="",columns:str="",user_question:str="",aggregation_columns:str="",conversation_id:str="",soeid:str="",*,user_id:str="")->dict:
 soeid=user_id or get_soeid()
 logger.info("tool_query_executor: resolved user_id=%s",soeid)
 start=time.time()
 config=_get_config(domain)
 try:
  rules_path=config.get_sql_validation_rules_path()
  if rules_path:validate_sql_query(sql_query,rules_path)
  from ..text2sql.utilities.db_adapter import execute_query
  env=config.get_deployment_env()
  db_type=config.get_db_type()
  raw_results=execute_query(sql_query=sql_query,env=env,db_type=db_type)
  if not raw_results:return{"status":"no_data","message":"Query executed successfully but returned no results.","row_count":0}
  df=pd.DataFrame(raw_results)
  for calc_fn in config.get_post_query_calculations():
   try:df=calc_fn(df,sql_query)
   except Exception as calc_err:logger.warning("Post-query calc failed: %s",calc_err)
  execution_key=f"{domain}_{uuid.uuid4().hex[:12]}_{int(time.time())}"
  parsed_columns:Dict[str,Any]={}
  if columns:
   try:parsed_columns=json.loads(columns)
   except json.JSONDecodeError:pass
  agg_cols=[c.strip()for c in aggregation_columns.split(",")if c.strip()]if aggregation_columns else[]
  store_data={"rows":df.to_dict("records"),"columns":parsed_columns,"aggregation_columns":agg_cols,"sql_query":sql_query,"user_question":user_question,"domain":domain,"soeid":soeid}
  query_result_store.store(execution_key,store_data)
  sample=df.head(5).to_dict("records")
  return{"status":"success","execution_key":execution_key,"row_count":len(df),"column_count":len(df.columns),"columns":list(df.columns),"sample_data":sample}
 except Exception as e:
  logger.error("Query executor error (domain=%s): %s",domain,e,exc_info=True)
  return{"status":"error","message":str(e)}
 finally:logger.info("[perf] query_executor(%s): %.2fs",domain,time.time()-start)
def tool_fuzzy_resolve(domain:str,column_name:str,fuzzy_input:str,top_k:int=5,*,user_id:str="")->dict:
 user_id=user_id or get_soeid()
 logger.info("tool_fuzzy_resolve: resolved user_id=%s",user_id)
 config=_get_config(domain)
 fuzzy_config=config.get_fuzzy_config()
 if not fuzzy_config:return{"status":"not_supported","message":f"Fuzzy resolution is not configured for domain '{domain}'."}
 enabled=fuzzy_config.get("enabled",False)
 logger.info("Fuzzy input handling: %s, fuzzy config enabled=%s",fuzzy_config,enabled)
 if not enabled:
  env_enabled=os.getenv("FUZZY_RESOLVER_ENABLED","").lower()=="true"or os.getenv("FUZZY_INPUT_HANDLING_ENABLED","").lower()=="true"
  if not env_enabled:return{"status":"disabled","message":"Fuzzy resolution is disabled. Set FUZZY_RESOLVER_ENABLED=true (or the legacy FUZZY_INPUT_HANDLING_ENABLED=true) to enable."}
 from ..text2sql.utilities.fuzzy_resolver.fuzzy_resolver_service import resolve_column_value
 try:
  matches=resolve_column_value(column_name=column_name,fuzzy_input=fuzzy_input,fuzzy_config=fuzzy_config,top_k=top_k)
  persona=None
  entitled_gfcids:List[str]=[]
  if domain=="credit_facility":
   from ..text2sql.domains.credit_facility.components import determine_user_persona
   persona=determine_user_persona(user_id)
   if persona=="NON_GSG":matches,entitled_gfcids=_filter_non_gsg_credit_facility_fuzzy_matches(matches=matches,soeid=user_id,column_name=column_name,env=config.get_deployment_env(),db_type=config.get_db_type())
  logger.info(" fuzzy suggestions are :%s",matches)
  response={"status":"success"if matches else"no_matches","column_name":column_name,"fuzzy_input":fuzzy_input,"matches":matches,"match_count":len(matches)}
  if persona:response["user_persona"]=persona
  if domain=="credit_facility":response["entitled_gfcids"]=entitled_gfcids
  return response
 except Exception as e:
  logger.error("Fuzzy resolve error: %s",e,exc_info=True)
  return{"status":"error","message":str(e)}
def tool_query_context(domain:str,user_query:str,gfcid:str="",gpnum:str="",client_level:str="",filter_criteria:str="",soeid:str="",platform:str="desktop",*,user_id:str="")->dict:
 soeid=user_id or get_soeid()
 logger.info("tool_query_context: resolved user_id=%s",soeid)
 start=time.time()
 config=_get_config(domain)
 try:
  effective_soeid=soeid
  preflight_result=_run_query_context_preflight(config,domain=domain,soeid=effective_soeid,gfcid=gfcid,gpnum=gpnum,client_level=client_level,filter_criteria=filter_criteria)
  if not preflight_result.get("ok",True):return{"status":"permission_denied","message":preflight_result.get("user_message","Unable to verify domain entitlements."),"reason":preflight_result.get("reason","entitlement_failed"),"retryable":bool(preflight_result.get("retryable",False)),"domain":domain}
  preflight_prompt_overrides=preflight_result.get("prompt_variable_overrides")
  if not isinstance(preflight_prompt_overrides,dict):preflight_prompt_overrides={}
  preflight_client_level=str(preflight_result.get("client_level")or"")
  preflight_filter_criteria=preflight_result.get("filter_criteria")
  effective_client_level=client_level or preflight_client_level
  load_ids:List[str]=[]
  as_of_date:Optional[str]=None
  needs_entitlement=bool(gfcid and config.get_entitlement_enabled())
  entitlement_template=config.get_entitlement_query_template()if needs_entitlement else None
  with ThreadPoolExecutor(max_workers=3)as pool:
   futures:Dict[str,Any]={}
   if entitlement_template:futures["entitlement"]=pool.submit(_check_entitlement,gfcid,effective_soeid,entitlement_template,config.get_deployment_env(),config.get_db_type())
   futures["load_ids"]=pool.submit(_initialize_load_ids_for_domain,config)
   futures["as_of_date"]=pool.submit(_initialize_as_of_date_for_domain,config)
   prefetch_timeout=float(os.getenv("TEXT2SQL_PREFETCH_TIMEOUT_SECONDS","120"))
   for key,future in futures.items():
    try:
     result=future.result(timeout=prefetch_timeout)
     if key=="entitlement":effective_client_level=client_level or result
     elif key=="load_ids":load_ids=result or[]
     elif key=="as_of_date":as_of_date=result
    except FuturesTimeoutError:
     logger.error("Task '%s' timed out after %.1fs.",key,prefetch_timeout)
     if key=="entitlement":raise RuntimeError(f"Entitlement check timed out for identifier {gfcid} after {prefetch_timeout:.0f}s")
    except Exception as exc:
     if key=="entitlement":raise
     logger.error("Parallel task '%s' failed: %s",key,exc)
  context=_compact_schema_context(config.get_schema_context())
  if isinstance(context,(dict,list)):context=json.dumps(context,separators=(",",":"))
  if load_ids:context+=f"\nThese are the available loadIds: {', '.join(map(str,load_ids))}."
  if as_of_date:context+=f"\nIMPORTANT - Data Freshness Date (last_load_date / as_of_date): {as_of_date}.\nAll date-based calculations MUST use this last_load_date instead of today's date.\n- YTM (Year-to-Month): Only include monthly columns from CY_01 up to the month of {as_of_date}.\n- L12M (Last 12 Months): The L12M column reflects the 12-month rolling window ending at {as_of_date}. Use it directly.\n- Do NOT include monthly columns for months after {as_of_date}."
  effective_filter_criteria=preflight_filter_criteria if preflight_filter_criteria is not None else filter_criteria
  effective_filter_criteria=_upsert_filter_criteria_value(effective_filter_criteria,"GFCID",gfcid)
  effective_filter_criteria=_upsert_filter_criteria_value(effective_filter_criteria,"GPNUM",gpnum)
  filter_instruction=_format_filter_criteria_for_prompt(effective_filter_criteria)
  full_user_query_parts=[f"{user_query} gfcid: {gfcid} gpnum: {gpnum} clientLevel: {effective_client_level}"]
  if filter_instruction:full_user_query_parts.append(filter_instruction)
  full_user_query="\n".join(full_user_query_parts)
  effective_date=as_of_date or str(datetime.date.today())
  domain_variables=config.get_prompt_variables(platform)
  domain_variables.update(config.get_text_to_sql_prompt_kwargs())
  domain_variables["input_context"]=context
  domain_variables["input_gfcid"]=gfcid
  domain_variables["input_gpnum"]=gpnum
  domain_variables["input_client_level"]=effective_client_level or""
  domain_variables["current_date"]=effective_date
  domain_variables["user_prompt"]=user_query
  _apply_prompt_variable_overrides(domain_variables,preflight_prompt_overrides)
  rules_path=config.get_sql_validation_rules_path()
  validation_rules:List[Dict[str,Any]]=[]
  if rules_path and os.path.isfile(rules_path):
   try:
    with open(rules_path,"r")as f:
     rules_yaml=yaml.safe_load(f)
     validation_rules=rules_yaml.get("rules",[])
   except Exception as exc:logger.warning("Failed to load validation rules: %s",exc)
  return{"status":"success","query_context_contract_version":"1.1.0","accepted_input_params":["domain","user_query","gfcid","gpnum","client_level","filter_criteria","platform"],"domain":domain,"schema_context":context,"domain_config":domain_variables,"user_prompt":user_query,"user_query_with_context":full_user_query,"entitlement_status":"granted","effective_client_level":effective_client_level or"","load_ids":load_ids,"as_of_date":as_of_date or"","filter_instruction":filter_instruction,"validation_rules":validation_rules,"gfcid":gfcid,"gpnum":gpnum,"platform":platform}
 except PermissionError as exc:
  logger.error("Entitlement denied (domain=%s): %s",domain,exc)
  return{"status":"error","error_type":"entitlement_denied","message":str(exc)}
 except Exception as e:
  logger.error("Query context error (domain=%s): %s",domain,e,exc_info=True)
  return{"status":"error","message":str(e)}
 finally:logger.info("[perf] query_context(%s): %.2fs",domain,time.time()-start)
def _compact_schema_context(schema:Any,max_values:int=25)->Any:
 if not isinstance(schema,dict):return schema
 compact=copy.deepcopy(schema)
 for table in compact.get("tables",[]):
  if not isinstance(table,dict):continue
  for col in table.get("columns",[]):
   if not isinstance(col,dict):continue
   pv=col.get("possible_values")
   if isinstance(pv,list)and len(pv)>max_values:
    extra=len(pv)-max_values
    col["possible_values"]=pv[:max_values]
    col["possible_values_note"]=f"...and {extra} more sample values (list truncated; use LIKE)"
 return compact
def tool_validate_sql(domain:str,sql_query:str,*,user_id:str="")->dict:
 user_id=user_id or get_soeid()
 logger.info("tool_validate_sql: resolved user_id=%s",user_id)
 config=_get_config(domain)
 rules_path=config.get_sql_validation_rules_path()
 if not rules_path:return{"status":"success","is_valid":True,"message":"No validation rules configured for this domain."}
 try:
  validate_sql_query(sql_query=sql_query,rules_file=rules_path)
  return{"status":"success","is_valid":True,"message":"SQL query passed all validation rules."}
 except Exception as exc:return{"status":"validation_failed","is_valid":False,"error_message":str(exc),"failed_rule":getattr(exc,"failed_rule",None)}
def tool_data_context(domain:str,execution_key:str,user_question:str="",columns:str="",aggregation_columns:str="",as_of_date:str="",client_identifier:str="",client_level:str="",gfcid_name:str="",platform:str="desktop",soeid:str="",*,user_id:str="")->dict:
 soeid=user_id or get_soeid()
 logger.info("tool_data_context: resolved user_id=%s",soeid)
 start=time.time()
 config=_get_config(domain)
 try:
  stored=query_result_store.retrieve(execution_key)
  if not stored:return{"status":"error","message":f"No data found for execution_key '{execution_key}'. Ensure the query_executor tool was called first."}
  rows=stored.get("rows",[])
  if not rows:return{"status":"no_data","message":"The stored result set is empty."}
  df=pd.DataFrame(rows)
  columns_payload=stored.get("columns",{})
  if columns:
   try:columns_payload=json.loads(columns)
   except json.JSONDecodeError:columns_payload=columns
  columns_dict=_normalize_column_metadata(columns_payload,df)
  agg_cols_list=_normalize_aggregation_columns(stored.get("aggregation_columns",[]))
  if aggregation_columns:agg_cols_list=_normalize_aggregation_columns(aggregation_columns)
  question=user_question or stored.get("user_question","")
  if not as_of_date:
   as_of_date=stored.get("as_of_date","")
   if not as_of_date:as_of_date=_initialize_as_of_date_for_domain(config)or""
  identifier_patterns=config.get_identifier_column_patterns()
  numeric_cols=_identify_numeric_columns(df,columns_dict,identifier_patterns)
  threshold=config.get_large_dataset_threshold(platform)
  is_large_dataset=len(df)>threshold
  business_aggregations=None
  if is_large_dataset:analysis=_build_compact_analysis_context(df=df,columns=columns_dict,user_question=question,aggregation_columns=agg_cols_list,numeric_columns=numeric_cols,identifier_patterns=identifier_patterns)
  else:
   analyzer=DataAnalyzer(aggregation_columns=agg_cols_list,numeric_columns=numeric_cols,identifier_patterns=identifier_patterns)
   analysis=analyzer.intelligent_data_reduction(df,include_full_data=True,enable_advanced_analytics=False,include_business_aggregations=bool(agg_cols_list))
  if agg_cols_list:
   agg_engine=BusinessAggregationEngine(aggregation_columns=agg_cols_list)
   business_aggregations=agg_engine.calculate_all_aggregations(df,numeric_columns=numeric_cols,identifier_patterns=identifier_patterns)
  authoritative_facts=_build_authoritative_facts(df,numeric_cols,agg_cols_list)
  if isinstance(analysis,dict):
   analysis.setdefault("authoritative_facts",authoritative_facts)
   cf_metrics=_build_credit_facility_verified_section(df)
   if cf_metrics:analysis["verified_business_metrics"]=cf_metrics
  if is_large_dataset:
   display_cols=_select_display_columns(df,question,agg_cols_list,numeric_cols,identifier_patterns)
   display_df=df[display_cols].head(threshold)
  else:display_df=df
  markdown_table=format_dataframe_to_markdown(display_df,numeric_columns=numeric_cols)
  summary_context=_build_summary_context(user_question=question,total_rows=len(df),columns=columns_dict,aggregation_columns=agg_cols_list,markdown_table=markdown_table,analysis_result=analysis,business_aggregations=business_aggregations,is_large_dataset=is_large_dataset,include_suggestions=True,as_of_date=as_of_date,client_identifier=client_identifier,client_level=client_level,gfcid_name=gfcid_name)
  verified_figures_parts=[]
  credit_facility_metrics=""
  if isinstance(analysis,dict):
   verified_figures=_format_authoritative_facts_for_summary(analysis.get("authoritative_facts"))
   if verified_figures:verified_figures_parts.append(verified_figures)
   credit_facility_metrics=analysis.get("verified_business_metrics","")
   if credit_facility_metrics:verified_figures_parts.insert(0,credit_facility_metrics)
  verified_figures="\n\n".join(verified_figures_parts)
  raw_results_markdown=_build_raw_results_markdown(df,numeric_cols)
  domain_variables=config.get_prompt_variables(platform)
  domain_variables.update(config.get_text_to_sql_prompt_kwargs())
  return{"status":"success","domain":domain,"domain_config":domain_variables,"sql_query":stored.get("sql_query",""),"summary_context":summary_context,"markdown_table":markdown_table,"raw_results_markdown":raw_results_markdown,"verified_figures":verified_figures,"verified_business_metrics":credit_facility_metrics,"total_rows":len(df),"displayed_rows":len(display_df),"numeric_columns":numeric_cols,"aggregation_columns":agg_cols_list,"as_of_date":as_of_date,"is_large_dataset":is_large_dataset,"columns":columns_dict,"user_question":question}
 except Exception as e:
  logger.error("Data context error (domain=%s): %s",domain,e,exc_info=True)
  return{"status":"error","message":str(e)}
 finally:logger.info("[perf] data_context(%s): %.2fs",domain,time.time()-start)