import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # loads .env file automatically

client = OpenAI(
    api_key=os.environ["QWEN_API_KEY"],
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)

resp = client.chat.completions.create(
    model="qwen-max",
    messages=[{"role": "user", "content": "Reply with: text model working"}],
)
print(resp.choices[0].message.content)