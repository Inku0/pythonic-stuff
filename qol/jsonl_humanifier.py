from jsonl import load

def bespoke_format(path):
    with open(path) as f:
        jsonl_data = load(f)
        for line in jsonl_data:
            # remove first line
            if "user_name" not in line and "characted_name" not in line:
                print(line["mes"]) if line["name"] == "Assistant" else None

if __name__ == "__main__":
    bespoke_format("text.jsonl")
