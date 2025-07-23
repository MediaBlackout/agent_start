import openai

# Set your OpenAI API key
openai.api_key = 'your-openai-api-key'

def call_openai_with_tools(messages, functions=None):
    """
    Calls OpenAI ChatCompletion with optional function calling.
    """

    response = openai.ChatCompletion.create(
        model="gpt-4-0613",  # or gpt-4 with tools depending on capabilities
        messages=messages,
        functions=functions,
        function_call="auto"
    )

    return response['choices'][0]['message']  # contains tool_call or response