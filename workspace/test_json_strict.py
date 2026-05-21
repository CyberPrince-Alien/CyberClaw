import json
try:
    print("With strict=False:", json.loads('{"x": "a\\nb"}', strict=False))
except Exception as e:
    print("strict=False failed:", e)
try:
    print("With strict=True:", json.loads('{"x": "a\\nb"}', strict=True))
except Exception as e:
    print("strict=True failed:", e)

# What about a literal newline character in the string?
try:
    print("Literal newline strict=False:", json.loads('{"x": "a\nb"}', strict=False))
except Exception as e:
    print("Literal newline strict=False failed:", e)
try:
    print("Literal newline strict=True:", json.loads('{"x": "a\nb"}', strict=True))
except Exception as e:
    print("Literal newline strict=True failed:", e)
