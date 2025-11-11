from loguru import logger
from trading_ig import IGService

class IGAuth:
    def __init__(self, api_key: str, username: str, password: str, account_type: str = "DEMO"):
        self.api_key = api_key
        self.username = username
        self.password = password
        self.account_type = account_type.upper()
        self.ig = None

    def login(self) -> IGService:
        logger.info(f"Logging in to IG ({self.account_type}) as {self.username}")
        self.ig = IGService(username=self.username, password=self.password, api_key=self.api_key, acc_type=self.account_type)
        self.ig.create_session()
        logger.success("IG session created.")
        return self.ig

    def logout(self):
        if self.ig:
            try:
                self.ig.logout()
                logger.info("Logged out from IG.")
            except Exception as e:
                logger.warning(f"Logout warning: {e}")
