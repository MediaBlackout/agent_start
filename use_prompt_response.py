# use_prompt_response.py

import os
from openai import OpenAI

# Set up your OpenAI API key environment variable or directly assign it
# os.environ["OPENAI_API_KEY"] = "your-api-key-here"

# Initialize OpenAI client
client = OpenAI()

# Define prompt payload with prompt ID and version
prompt_payload = {
    "id": "pmpt_68702538ad2481958a150a6538d02ad90b7c27995ac44c36",
    "version": "1"
}

# Function to get response from a prompt
def get_prompt_response(prompt):
    try:
        response = client.responses.create(
            prompt=prompt
        )
        return response
    except Exception as e:
        print(f"Error occurred while fetching response: {e}")
        return None

# Main execution
def main():
    response = get_prompt_response(prompt_payload)
    if response:
        print("Response Text:")
        # Depending on response object structure, adapt accordingly
        print(response.text if hasattr(response, "text") else response)

if __name__ == "__main__":
    main()
