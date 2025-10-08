from json import loads

import httpx
import webhook_listener

from utils.read_env import read_env


class RBClient:
    def __init__(self) -> None:
        config = read_env()
        self.base_url: str = config.get("RB_URL")
        self.schema: str = config.get("RB_SCHEMA", "http")
        self.port: str = config.get("RB_PORT", "4000")
        self.username: str = config.get("RB_USERNAME")
        self.password: str = config.get("RB_PASSWORD")
        missing_vars = []
        if self.base_url is None:
            missing_vars.append("RB_URL")
        if self.username is None:
            missing_vars.append("RB_USERNAME")
        if self.password is None:
            missing_vars.append("RB_PASSWORD")
        if missing_vars:
            raise ValueError(f"Missing required environment variable(s): {', '.join(missing_vars)}")
        self.full_url: str = f"{self.schema}://{self.base_url}:{self.port}"

    def get_status(self):
        try:
            response = httpx.get(
                f"{self.full_url}/status", auth=(self.username, self.password)
            )
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            return {"error": f"Network error: {str(e)}"}
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error: {str(e)}"}
        except ValueError as e:
            return {"error": f"Invalid JSON response: {str(e)}"}

    def pause(self):
        print("pausing RainbowMiner...")
        try:
            response = httpx.get(
                f"{self.full_url}/pause?action=set", auth=(self.username, self.password)
            )
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            return {"error": f"Network error: {str(e)}"}
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error: {str(e)}"}
        except ValueError as e:
            return {"error": f"Invalid JSON response: {str(e)}"}

    def resume(self):
        print("resuming RainbowMiner...")
        try:
            response = httpx.get(
                f"{self.full_url}/pause?action=reset", auth=(self.username, self.password)
            )
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            return {"error": f"Network error: {str(e)}"}
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP error: {str(e)}"}
        except ValueError as e:
            return {"error": f"Invalid JSON response: {str(e)}"}

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
