Starts a 1-thread webserver which listens for webhooks (from Jellyfin) on port 6666.

If it receives a webhook with "Play": "True" in its body, it pauses RainbowMiner. If the body includes "Play": "False", it resumes it.

`.env` must include the following:

```.env
RB_URL=
RB_SCHEMA=
RB_PORT=
RB_USERNAME=
RB_PASSWORD=
```
