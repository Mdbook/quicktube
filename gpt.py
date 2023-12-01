import requests

prefix = """Your output should use the following template:
## Summary
[summary text]
### Highlights
- Bulletpoint

Your task is to summarise the text I have given you in up to seven concise bullet points, starting with a short overview of the content."""

def summarize(content, key):
    # Create the JSON payload
    token = key
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": prefix},
            {"role": "user", "content": content},
        ],
        "temperature": 0.0,
    }

    # Make the API request
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    response = requests.post(
        "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
    )
    response.raise_for_status()

    # Parse the response
    data = response.json()
    result = data["choices"][0]["message"]["content"]
    return result
