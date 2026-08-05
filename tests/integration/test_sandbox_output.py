from agents.generator.sandbox import run_in_isolated_sandbox


def test_sandbox_console_output():
    code = """
print("Hello from inside the sandbox!")
print("Generating mock records...")
for i in range(3):
    print(f"Record {i+1} created successfully.")
"""
    success, message = run_in_isolated_sandbox(code)
    assert success is True
    assert "<console_output>" in message
    assert "Record 3 created successfully." in message
