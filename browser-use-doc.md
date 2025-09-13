import asyncio

from browser_use import Agent, Browser, ChatOpenAI

# NOTE: This is still experimental, and agents might conflict each other.


async def main():
	# Create 3 separate browser instances
	browsers = [
		Browser(
			user_data_dir=f'./temp-profile-{i}',
			headless=False,
		)
		for i in range(3)
	]

	# Create 3 agents with different tasks
	agents = [
		Agent(
			task='Search for "browser automation" on Google',
			browser=browsers[0],
			llm=ChatOpenAI(model='gpt-4.1-mini'),
		),
		Agent(
			task='Search for "AI agents" on DuckDuckGo',
			browser=browsers[1],
			llm=ChatOpenAI(model='gpt-4.1-mini'),
		),
		Agent(
			task='Visit Wikipedia and search for "web scraping"',
			browser=browsers[2],
			llm=ChatOpenAI(model='gpt-4.1-mini'),
		),
	]

	# Run all agents in parallel
	tasks = [agent.run() for agent in agents]
	results = await asyncio.gather(*tasks, return_exceptions=True)

	print('🎉 All agents completed!')


if __name__ == '__main__':
	asyncio.run(main())


AWS Bedrock example
AWS Bedrock provides access to multiple model providers through a single API. We support both a general AWS Bedrock client and provider-specific convenience classes.
AWS Authentication
Required environment variables:
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1

import asyncio
from dotenv import load_dotenv
load_dotenv()
from browser_use import Agent, ChatOpenAI

async def main():
    agent = Agent(
        task="Find the number of stars of the browser-use repo",
        llm=ChatOpenAI(model="gpt-4.1-mini"),
    )
    await agent.run()

asyncio.run(main())

from browser_use import Agent, ChatAWSBedrock

# Works with any Bedrock model (Anthropic, Meta, AI21, etc.)
llm = ChatAWSBedrock(
    model="anthropic.claude-3-5-sonnet-20240620-v1:0",  # or any Bedrock model
    aws_region="us-east-1",
)

# Create agent with the model
agent = Agent(
    task="Your task here",
    llm=llm
)


import asyncio
from dotenv import load_dotenv
load_dotenv()

from browser_use import Agent, BrowserProfile

# Speed optimization instructions for the model
SPEED_OPTIMIZATION_PROMPT = """
Speed optimization instructions:
- Be extremely concise and direct in your responses
- Get to the goal as quickly as possible
- Use multi-action sequences whenever possible to reduce steps
"""


async def main():
	# 1. Use fast LLM - Llama 4 on Groq for ultra-fast inference
	from browser_use import ChatGroq

	llm = ChatGroq(
		model='meta-llama/llama-4-maverick-17b-128e-instruct',
		temperature=0.0,
	)
	# from browser_use import ChatGoogle

	# llm = ChatGoogle(model='gemini-2.5-flash')

	# 2. Create speed-optimized browser profile
	browser_profile = BrowserProfile(
		minimum_wait_page_load_time=0.1,
		wait_between_actions=0.1,
		headless=False,
	)

	# 3. Define a speed-focused task
	task = """
	1. Go to reddit https://www.reddit.com/search/?q=browser+agent&type=communities 
	2. Click directly on the first 5 communities to open each in new tabs
    3. Find out what the latest post is about, and switch directly to the next tab
	4. Return the latest post summary for each page
	"""

	# 4. Create agent with all speed optimizations
	agent = Agent(
		task=task,
		llm=llm,
		flash_mode=True,  # Disables thinking in the LLM output for maximum speed
		browser_profile=browser_profile,
		extend_system_message=SPEED_OPTIMIZATION_PROMPT,
	)

	await agent.run()


if __name__ == '__main__':
	asyncio.run(main())

# Follow up tasks

> Follow up tasks with the same browser session.

## Chain Agent Tasks

Keep your browser session alive and chain multiple tasks together. Perfect for conversational workflows or multi-step processes.

```python
from dotenv import load_dotenv

from browser_use import Agent, Browser


load_dotenv()

import asyncio


async def main():
	browser = Browser(keep_alive=True)

	await browser.start()

	agent = Agent(task='search for browser-use.', browser_session=browser)
	await agent.run(max_steps=2)
	agent.add_new_task('return the title of first result')
	await agent.run()

	await browser.kill()

asyncio.run(main())
```

## How It Works

1. **Persistent Browser**: `BrowserProfile(keep_alive=True)` prevents browser from closing between tasks
2. **Task Chaining**: Use `agent.add_new_task()` to add follow-up tasks
3. **Context Preservation**: Agent maintains memory and browser state across tasks
4. **Interactive Flow**: Perfect for conversational interfaces
5. **Break down long flows**: If you have very long flows, you can keep the browser alive and send new agents to it.

<Note>
  The browser session remains active throughout the entire chain, preserving all cookies, local storage, and page state.
</Note>
