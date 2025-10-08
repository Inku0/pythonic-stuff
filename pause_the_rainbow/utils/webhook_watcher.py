import webhook_listener


def process_post_request(request, *args, **kwargs):
    print(
        "Received request:\n"
        + "Method: {}\n".format(request.method)
        + "Headers: {}\n".format(request.headers)
        + "Args (url path): {}\n".format(args)
        + "Keyword Args (url parameters): {}\n".format(kwargs)
        + "Body: {}".format(
            request.body.read(int(request.headers["Content-Length"]))
            if int(request.headers.get("Content-Length", 0)) > 0
            else ""
        )
    )

    # Process the request!
    # ...

    return


def start_webhook_watcher():
    webhooks = webhook_listener.Listener(
        handlers={"POST": process_post_request}, port=3084, threadPool=1, logScreen=True
    )
    webhooks.start()
