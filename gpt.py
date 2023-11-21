import requests

prefix = "You are a helpful assistant. Please briefly summarize the following content for the user. Format your summary in Markdown, in the format of a brief bullet-point summary for each new topic discussed."


def summarize(content, key):
    # Create the JSON payload
    token = key
    payload = {
        "model": "gpt-4-0613",
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
