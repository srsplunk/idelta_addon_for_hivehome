import json
import logging
import requests

import import_declare_test
from solnlib import conf_manager, log
from splunklib import modularinput as smi
from pyhiveapi import Hive



ADDON_NAME = "idelta_addon_for_hivehome"


def logger_for_input(input_name: str) -> logging.Logger:
    return log.Logs().get_logger(f"{ADDON_NAME.lower()}_{input_name}")


def get_device_credentials(session_key: str, account_name: str):
    cfm = conf_manager.ConfManager(
        session_key,
        ADDON_NAME,
        realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-idelta_addon_for_hivehome_account",
    )
    account_conf_file = cfm.get_conf("idelta_addon_for_hivehome_account")
    return account_conf_file.get(account_name).get("hive_username"),account_conf_file.get(account_name).get("hive_password"), account_conf_file.get(account_name).get("device_group_key"), account_conf_file.get(account_name).get("device_key"),account_conf_file.get(account_name).get("device_password")

def device_auth(logger: logging.Logger, hive_username: str,hive_password: str,device_group_key: str,device_key: str,device_password: str):
    logger.info("Starting Hive Device Authentication")
    session = Hive(
        username=hive_username,
        password=hive_password)
    session.auth.device_group_key=device_group_key
    session.auth.device_key=device_key
    session.auth.device_password=device_password
    logger.info("Running deviceLogin()")
    session.deviceLogin()
    return session.tokens


def get_data_from_api(logger: logging.Logger, session_token: str):


    logger.info("Getting data from an Hive API nodes endpoint")
    url = "https://api.prod.bgchprod.info:443/omnia/nodes"
    payload = {}
    headers = {
        'Content-Type': 'application/vnd.alertme.zoo-6.1+json',
        'Accept': 'application/vnd.alertme.zoo-6.1+json',
        'X-Omnia-Client': 'Hive Web Dashboard',
        'X-Omnia-Access-Token': session_token
        }
    response = requests.request("GET", url, headers=headers, data=payload)
    response_json = json.loads(response.text)
    return response_json


def validate_input(definition: smi.ValidationDefinition):
    return


def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    # inputs.inputs is a Python dictionary object like:
    # {
    #   "get_nodes://<input_name>": {
    #     "account": "<account_name>",
    #     "disabled": "0",
    #     "host": "$decideOnStartup",
    #     "index": "<index_name>",
    #     "interval": "<interval_value>",
    #     "python.version": "python3",
    #   },
    # }
    for input_name, input_item in inputs.inputs.items():
        normalized_input_name = input_name.split("/")[-1]
        logger = logger_for_input(normalized_input_name)
        try:
            session_key = inputs.metadata["session_key"]
            log_level = conf_manager.get_log_level(
                logger=logger,
                session_key=session_key,
                app_name=ADDON_NAME,
                conf_name=f"{ADDON_NAME}_settings",
            )
            logger.setLevel(log_level)
            log.modular_input_start(logger, normalized_input_name)
            #get the data required for authentication:
            hive_username,hive_password,device_group_key,device_key,device_password = get_device_credentials(session_key, input_item.get("account"))
            logger.debug("hive username: "+hive_username)
            logger.debug("hive password: "+hive_password)
            logger.debug("device group key: "+device_group_key)
            logger.debug("device key: "+device_key)
            logger.debug("device password: "+device_password)
            #perform authentication and get the session tokens
            session_tokens = device_auth(logger,hive_username,hive_password,device_group_key,device_key,device_password)
            #call the API endpoint to get the nodes data
            data = get_data_from_api(logger, session_tokens["tokenData"]["token"]) 
            sourcetype = "hive:nodes"
            for line in data["nodes"]:
                event_writer.write_event(
                    smi.Event(
                        data=json.dumps(line, ensure_ascii=False, default=str),
                        index=input_item.get("index"),
                        sourcetype=sourcetype,
                    )
                )
            log.events_ingested(
                logger,
                input_name,
                sourcetype,
                len(data),
                input_item.get("index"),
                account=input_item.get("account"),
            )
            log.modular_input_end(logger, normalized_input_name)
        except Exception as e:
            log.log_exception(logger, e, "my custom error type", msg_before="Exception raised while ingesting data for demo_input: ")
