from orchestrator.orchestrator import OrchestratorAgent
from config.logging_config import configure_logging


configure_logging()

def main():
    pr_url = input("Enter PR URL: ")
    OrchestratorAgent().run(pr_url)

if __name__ == "__main__":
    main()