api_key = None

class Embedding:
    @staticmethod
    def create(*args, **kwargs):
        return {"data": [{"embedding": []}]}

class Completion:
    @staticmethod
    def create(*args, **kwargs):
        return type("Resp", (), {"choices": [type("Choice", (), {"text": ""})()]})()
