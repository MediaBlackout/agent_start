import os

def create_agent_file(filename="agent_test_1.py"):
    code = '''\
import os
import openai

def main():
    # Ensure your OpenAI API Key is set in the environment
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        return

    openai.api_key = openai_api_key

    print("Welcome to OpenAI Agent. Type 'exit' to quit.")

    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            print("Goodbye!")
            break

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Change to preferred model
                messages=[
                    {{"role": "user", "content": user_input}}
                ]
            )
            reply = response['choices'][0]['message']['content']
            print("Agent:", reply.strip())

        except Exception as e:
            print("An error occurred during API call:", e)

if __name__ == "__main__":
    main()
'''

    with open(filename, 'w') as f:
        f.write(code)
    print(f"{filename} created successfully.")

if __name__ == "__main__":
    create_agent_file()
