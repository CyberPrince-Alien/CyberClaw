import re
import json
import uuid

# Define LLMToolCall mock
class LLMToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.name = name
        self.arguments = arguments
    def __repr__(self):
        return f"LLMToolCall(id={self.id}, name={self.name}, arguments={self.arguments})"

def _parse_fallback_tool_calls(content: str) -> list:
    tool_calls = []
    
    # Try to find all ```json ... ``` blocks
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    
    # If no code blocks, try to find raw JSON strings { ... }
    if not json_blocks:
        matches = re.findall(r"(\{.*?\})", content, re.DOTALL)
        if matches:
            json_blocks = matches

    print(f"DEBUG: json_blocks found: {json_blocks}")

    for block in json_blocks:
        try:
            data = json.loads(block.strip(), strict=False)
            print(f"DEBUG: loaded data: {data}")
            if isinstance(data, dict):
                if "name" in data and "arguments" in data:
                    args = data["arguments"]
                    if not isinstance(args, str):
                        args = json.dumps(args)
                    tool_calls.append(
                        LLMToolCall(
                            id=f"fallback-{uuid.uuid4().hex[:8]}",
                            name=data["name"],
                            arguments=args,
                        )
                    )
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item and "arguments" in item:
                        args = item["arguments"]
                        if not isinstance(args, str):
                            args = json.dumps(args)
                        tool_calls.append(
                            LLMToolCall(
                                id=f"fallback-{uuid.uuid4().hex[:8]}",
                                name=item["name"],
                                arguments=args,
                            )
                        )
        except Exception as e:
            print(f"DEBUG: error parsing block: {e}")
            
    return tool_calls

# Content from user's terminal
content_1 = """```json
{"name": "bash", "arguments": {"command": "open -a \\"Google Chrome\\" 2>/dev/null || google-chrome 2>/dev/null || start\\nchrome 2>/dev/null || echo \\"Cannot detect Chrome installation\\""}}
```"""

content_2 = """```json
{"name": "bash", "arguments": {"command": "open \\"https://youtube.com\\""}}
```"""

print("Testing content 1:")
print(_parse_fallback_tool_calls(content_1))

print("\\nTesting content 2:")
print(_parse_fallback_tool_calls(content_2))
