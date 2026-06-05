"""HF Spaces entry point — bridge to the real Gradio app."""

from finance_agent.app import demo

if __name__ == "__main__":
    demo.launch()
