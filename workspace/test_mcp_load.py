import asyncio
import logging
from pathlib import Path
from cyberclaw.utils.config import Config
from cyberclaw.core.context import SharedContext
from cyberclaw.core.agent import Agent
from cyberclaw.core.events import CliEventSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

async def test_mcp():
    workspace_dir = Path(__file__).parent.resolve()
    print(f"Loading config from workspace: {workspace_dir}")
    
    # Load config
    config = Config.load(workspace_dir)
    print(f"Configured MCP servers: {config.mcp_servers}")
    
    # Create context
    context = SharedContext(config=config, channels=[])
    
    # Load default agent
    agent_id = config.default_agent
    agent_def = context.agent_loader.load(agent_id)
    
    # Create session
    agent = Agent(agent_def, context)
    session = agent.new_session(CliEventSource())
    
    print("\nEnsuring MCP servers are initialized...")
    await session._ensure_mcp_initialized()
    
    print("\nRegistered Tools in Session:")
    for t in session.tools.list_all():
        print(f" - {t.name}: {t.description}")
        
    print("\nAll done!")

if __name__ == "__main__":
    asyncio.run(test_mcp())
