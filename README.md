# AutoDev - Autonomous Development System

A long-running agent harness for autonomous software development, based on Anthropic's multi-context window workflow design principles.

## Overview

AutoDev is designed to autonomously develop software by breaking down projects into manageable features and iteratively implementing them. The system maintains context across sessions, enabling continuous progress on complex development tasks.

## Features

- **Initializer Agent**: Sets up the project environment and generates feature lists from specifications
- **Coder Agent**: Makes incremental progress on features using LLM-powered coding
- **Feature List Management**: Track and manage development tasks with priorities and status
- **Progress Tracking**: Persistent progress tracking across coding sessions
- **E2E Testing Support**: Built-in end-to-end testing capabilities
- **Session Recovery**: Recover context and continue work from previous sessions

## Installation

```bash
# Clone the repository
git clone https://github.com/aifly-commit/autodev-system.git
cd autodev-system

# Install dependencies
pip install -e .
```

## Quick Start

### 1. Initialize a Project

```bash
# Basic initialization
autodev init /path/to/your/project --spec "Your project specification"

# With AI-generated feature list (requires ANTHROPIC_API_KEY)
autodev init /path/to/your/project --spec-file spec.md --run-agent
```

### 2. View Project Status

```bash
# Check project status
autodev status /path/to/your/project

# View feature list
autodev feature-list /path/to/your/project

# View session context
autodev context /path/to/your/project
```

### 3. Run Development

```bash
# Run the autonomous development loop
autodev run /path/to/your/project

# Run a single coding session
autodev session /path/to/your/project
```

## Project Structure

```
autodev-system/
├── cli.py                 # Command-line interface
├── core/                  # Core modules
│   ├── harness.py         # Main controller
│   ├── config.py          # Configuration management
│   ├── models.py          # Data models
│   ├── llm_client.py      # LLM client
│   ├── agents/            # Agent implementations
│   │   ├── base.py        # Base agent class
│   │   ├── coder.py       # Coding agent
│   │   └── initializer.py # Initializer agent
│   └── tools/             # Tool implementations
│       ├── git_ops.py     # Git operations
│       ├── test_runner.py # Test execution
│       └── browser_automation.py # Browser tools
├── config/                # Configuration files
├── templates/             # Project templates
└── tests/                 # Test suite
```

## Configuration

AutoDev uses YAML configuration files. Default configuration is stored in `config/settings.yaml`.

Key configuration options:

```yaml
execution:
  max_iterations: 100      # Maximum coding iterations

paths:
  autodev_dir: .autodev    # AutoDev working directory
  feature_list: features.json
  progress_file: progress.md

logging:
  level: INFO
```

## Requirements

- Python 3.10+
- Anthropic API key (for AI-powered features)

## Environment Variables

```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

This project is inspired by Anthropic's design principles for multi-context window workflows and long-running agent systems.
