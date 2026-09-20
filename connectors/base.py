from abc import ABC, abstractmethod


class BaseConnector(ABC):

    @abstractmethod
    def execute(
        self,
        action,
        business_id,
        user_id,
    ):
        raise NotImplementedError