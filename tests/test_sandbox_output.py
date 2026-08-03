import os
import sys

# Ensure UTF-8 stdout on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from dotenv import load_dotenv
load_dotenv()

from agents.generator.sandbox import run_in_isolated_sandbox

def test_sandbox_console_output():
    code = """
print("Hello from inside the sandbox!")
print("Generating mock records...")
for i in range(3):
    print(f"Record {i+1} created successfully.")
"""
    success, message = run_in_isolated_sandbox(code)
    print(f"Success: {success}")
    print("--- Message Output ---")
    print(message)
    print("----------------------")
    
    assert success is True
    assert "<console_output>" in message
    assert "Record 3 created successfully." in message
    print("\n✅ Test passed! Console output correctly captured and wrapped in XML tags.")

if __name__ == "__main__":
    test_sandbox_console_output()
