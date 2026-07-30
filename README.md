# Agentic AI for AAS-Based Data Pipeline Generation in Industry 4.0

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

An Asset Administration Shell (AAS) approach for representing, generating, and deploying industrial data pipelines using agentic workflows and the Model Context Protocol (MCP).

---

## Abstract

Industrial data pipelines are essential for transforming heterogeneous shop-floor data into usable information, yet their engineering remains predomi-nantly manual and difficult to reuse across changing manufacturing envi-ronments. Engineers must repeatedly interpret asset capabilities, redefine da-ta transformations, configure storage and processing services, and maintain these configurations as industrial systems evolve. This lack of machine-interpretable pipeline models restricts interoperability, increases deployment effort, and limits the adaptability expected from Industry 4.0 systems. This paper presents an Asset Administration Shell (AAS) approach for represent-ing, generating, and deploying industrial data pipelines. First, it extends ex-isting data management AAS submodels with a reusable data-pipeline model structured around collection, integration, preprocessing, storage, processing, and utilization stages. Second, it introduces an agentic workflow that inter-prets AAS-described assets through an AAS Model Context Protocol server. Third, it formulates pipeline configurations, validates execution plans with human supervision, and deploys the required software components. A con-tainerized prototype demonstrates the creation, deployment, reuse, and ex-tension of pipelines connecting robotic, messaging, storage, and visualiza-tion components. By treating data pipelines as first-class AAS artefacts, the proposed approach establishes a semantic foundation for more interoperable, reusable, and human-supervised industrial data engineering.
---

## Architecture Overview

The system follows a two-layer agentic architecture that can be divided in two parts: an Agentic Pipeline Builder and a MCP Building Section Architecture.


![Agentic Architecture](multi_agent_architecture.png)

* **Layer 1 (Interaction & Directing):** The user interacts directly with the **Agentic Pipeline Builder**, which is responsible for interacting with the User and AAS to build and deploy data pipelines. While also communicating with the **Orchestrator** inside the MCP building environment to build new MCP infraestructure.
* **Layer 2 (Execution & Refinement):** The **Orchestrator** manages dedicated sub-agents:
  * **Researcher:** Does websearch to gather additional information to supplement the AAS and to give a fuller picture to the next agent.
  * **Generator:** Formulates MCP infraestrucute for AAS assets that are represeted and don't have a dedicated MCP server in order to enable deployment.
  * **Reviewer:** Validates the MCP code generated and makes improvement suggestions.



## Getting Started

### Prerequisites
- Docker 
- Python 3.10+
- `uv` package manager (recommended)

### 1. Launch Infrastructure Services

Clone the repository and bring up the containerized infrastructure (BaSyx, Kafka, MongoDB, SearXNG, etc.):

```bash
# Clone the repository
git clone https://github.com/NOVA-RICS-Open-Lab/agentic-data-pipelines.git
cd agentic-data-pipelines

# Copy environment template if needed
cp .env.example .env  # Configure your API keys (OPENAI_API_KEY, etc.)

# Launch all Docker services
docker compose --profile http up -d
```

Verify that services are active:
* **AAS Server**: `http://localhost:5051`
* **AAS Server UI**: `http://localhost:5040`
* **AAS Registry**: `http://localhost:5010`
* **Submodel Registry**: `http://localhost:5020`

### 2. Agent Interaction

Once started, open your browser at **`http://localhost:8000`** to interact with the Agentic Builder.

---

### ## Citation

If you use or build on this work, please cite:

​```bibtex
@mastersthesis{miranda2026agentic,
  author  = {Miranda, João and Pegado, António and Freitas, Nelson and Rocha, André and Barata, José},
  title   = {Agentic AI for AAS-Based Data Pipeline Generation in Industry 4.0},
  school  = {NOVA School of Science and Technology},
  year    = {2026}
}
​```

## License

This repository is released under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contacts

For questions about this or other projects, contact us at [novaricsopenlab@gmail.com](mailto:novaricsopenlab@gmail.com) or join our [Discussion Forum](https://github.com/NOVA-RICS-Open-Lab/agentic-data-pipelines/discussions).