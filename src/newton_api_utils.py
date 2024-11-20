import dataclasses, typing, requests, os, time
import pyodbc
import pandas as pd

#suppress warnings
import warnings
warnings.filterwarnings('ignore')


def build_api_header(user_id, use_qa_env=False):
    if not use_qa_env:
        secrets = {
            'a-secret': 'D97Sg85rqrVOtA8S0HLC1QOswCALfV2wrEXbXjunvsJ2e66EEfdOaicTBOSB0he3',
            'a-client': 'r7ISZQvA1en3Iz50yyCarO4TpYwWO9SK',
            'auth-url':  'https://signin.pinnacleauth.com/oauth/token',
            'client-id': '3eTKslHvRx0NypB955pX7g8SGzxe7jG9',
            'secret': 'CYF04Ww5-cZS7UUys2WdoLUwUr4xDBa3pxWK0vExpo0TSdHYXedjgdxkLCeXrMBI',
            'audience': 'https://api.pinnacletech.com',
            'grant-type': 'client_credentials',
            'user-id': user_id #this is the user id of the user that the token will be impersonating. Replace this with the user id of the user you want to impersonate
        }

        api_url = "https://newton.pinnacletech.com/pinnpetrol/api/scenario/179479048/inspection/import"
    else:
        secrets = {
            'a-secret': 'D97Sg85rqrVOtA8S0HLC1QOswCALfV2wrEXbXjunvsJ2e66EEfdOaicTBOSB0he3',
            'a-client': 'r7ISZQvA1en3Iz50yyCarO4TpYwWO9SK',
            'auth-url':  'https://qa-signin.pinnacleauth.com/oauth/token',
            'client-id': 'TlMOvTJu8P4USXHjkw7QFdhJ4JCL6QCE',
            'secret': 't7ysUSWyWOTZPZwUOU-_5S9SYp0pbjd2E-vb9pXx365-45oNrr2WJcg1A2vYHoYa',
            'audience': 'https://api.pinnacletech.com',
            'grant-type': 'client_credentials',
            'user-id': user_id #this is the user id of the user that the token will be impersonating. Replace this with the user id of the user you want to impersonate
        }
        api_url = "https://qa-newton.pinnacletech.com/pinnpetrol/api/scenario/179479048/inspection/import"

    # from dotenv import load_dotenv

    # load_dotenv(env_file_path)

    @dataclasses.dataclass
    class Auth0Payload:
        client_id: str
        client_secret: str
        audience: str
        grant_type: str
        def to_dictionary(self) -> typing.Dict[str, str]:
            return dataclasses.asdict(self)

    @dataclasses.dataclass
    class Auth0Settings:
        url: str
        client_id: str
        client_secret: str
        audience: str
        grant_type: str

        def to_payload(self) -> Auth0Payload:
            return Auth0Payload(self.client_id, self.client_secret, self.audience, self.grant_type)

    @dataclasses.dataclass
    class ApiSettings:
        url: str
        access_token: str
        impersonated_user_id: str

    def get_access_token(settings: Auth0Settings) -> str:
        payload = settings.to_payload().to_dictionary()
        r = requests.post(settings.url, json=payload)
        r.raise_for_status()
        response_json = r.json()
        return response_json['access_token']

    # auth_url = os.getenv('newton_prod_url')
    # auth_client_id = os.getenv('newton_prod_clientid')
    # auth_secret = os.getenv('newton_prod_secret')
    # auth_audience = os.getenv('newton_prod_audience')
    # auth_grant_type = os.getenv('newton_prod_type')
    # impersonated_user_id = os.getenv('newton_prod_user_id')

    auth_url = secrets['auth-url']
    auth_client_id = secrets['client-id']
    auth_secret = secrets['secret']
    auth_audience = secrets['audience']
    auth_grant_type = secrets['grant-type']
    impersonated_user_id = secrets['user-id']



    token_settings = Auth0Settings(
        auth_url,
        auth_client_id,
        auth_secret,
        auth_audience,
        auth_grant_type
    )
    access_token = get_access_token(token_settings)

    header = {
        'authorization': f'Bearer {access_token}',
        'user': impersonated_user_id
    }
    return header

def query_newton_db(filter_parameters={}, query=None):
    replacements = {}
    if filter_parameters != {}:
        for key, value in filter_parameters.items():
            replacements[f'_replace_me_with_{key}_'] = value
        
    # run a query and return the results as a dataframe
    server = "sqldb-newton-prod-eastus2.database.windows.net"
    database = 'crs'
    username = 'crs_reader'
    password = 'hbWA08wrmAA3B3'
    driver= '{SQL Server}'
    query = f'./support_files/{query}.sql'

    with open(query, "r") as file:
        query = file.read()
        for key, value in replacements.items():
            query = query.replace(key, value)
        
        with pyodbc.connect('DRIVER='+driver+';SERVER='+server+';PORT=1433;DATABASE='+database+';UID='+username+';PWD='+ password) as conn:
            #print(query)
            df = pd.read_sql(query, conn)
            
        # convert the df to a dictionary
        results_dict = df.to_dict(orient='records')
        return results_dict

    




