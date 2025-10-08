from json import loads

import httpx
import webhook_listener

from utils.read_env import read_env


class RBClient:
    def __init__(self) -> None:
        config = read_env()
        try:
            self.base_url: str = config.get("RB_URL")
            self.schema: str = config.get("RB_SCHEMA", "http")
            self.port: str = config.get("RB_PORT", "4000")
            self.username: str = config.get("RB_USERNAME")
            self.password: str = config.get("RB_PASSWORD")
            self.full_url: str = f"{self.schema}://{self.base_url}:{self.port}"
        except KeyError as e:
            raise ValueError(f"Missing required environment variable: {e}")

    def get_status(self):
        status = httpx.get(
            f"{self.full_url}/status", auth=(self.username, self.password)
        )
        return status.json()

    def pause(self):
        print("pausing RainbowMiner...")
        result = httpx.get(
            f"{self.full_url}/pause?action=set", auth=(self.username, self.password)
        )
        return result.json()

    def resume(self):
        print("resuming RainbowMiner...")
        result = httpx.get(
            f"{self.full_url}/pause?action=reset", auth=(self.username, self.password)
        )
        return result.json()

    def process_post_request(self, request, *args, **kwargs) -> None:
        # print(
        #     "Received request:\n"
        #     + "Method: {}\n".format(request.method)
        #     + "Headers: {}\n".format(request.headers)
        #     + "Body: {}".format(
        #         request.body.read(int(request.headers["Content-Length"]))
        #         if int(request.headers.get("Content-Length", 0)) > 0
        #         else ""
        #     )
        # )

        body_raw = (
            request.body.read(int(request.headers["Content-Length"]))
            if int(request.headers.get("Content-Length", 0)) > 0
            else "{}"
        )
        body: dict[str, str] = loads(body_raw.decode("utf-8"))

        if body.get("Play") == "True":
            self.pause()
        elif body.get("Play") == "False":
            self.resume()

        return

    def start_webhook_watcher(self) -> None:
        webhooks = webhook_listener.Listener(
            handlers={"POST": self.process_post_request},
            port=6666,
            threadPool=1,
            logScreen=True,
        )
        webhooks.start()
