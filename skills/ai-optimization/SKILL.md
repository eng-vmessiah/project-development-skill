---
name: ai-optimization
description: "AI-powered optimization patterns — prompt tuning, code improvement, agent architecture discovery. Use when optimizing prompts, improving AI outputs, or finding better configurations."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [ai, optimization, prompts, evolutionary, reflection, gepa]
    related_skills: [ai-regression-testing, clean-code, design-patterns, humanizer]
---

# AI Optimization Patterns

## Overview

Optimize any text parameter — prompts, code, agent architectures, configurations — using LLM-based reflection and evolutionary search.

**Based on:** GEPA (Genetic-Pareto) framework and reflective optimization patterns.

## When to Use

- Prompt quality is suboptimal
- AI outputs need improvement
- Finding better configurations
- Agent architecture tuning
- Code optimization with AI feedback

## Core Concept: Reflective Evolution

Traditional optimizers know *that* a candidate failed but not *why*. Reflective optimization:

1. **Execute** — Run candidate on task, capture full traces
2. **Reflect** — LLM reads traces (errors, profiling, reasoning) and diagnoses failures
3. **Mutate** — Generate improved candidate informed by accumulated lessons
4. **Select** — Keep if improved, update Pareto front

```
┌─────────────────────────────────────────────────────────────┐
│                    OPTIMIZATION LOOP                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   Candidate ──► Execute ──► Trace ──► Reflect ──► Mutate    │
│      ▲                                      │               │
│      └──────────────────────────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Pattern 1: Prompt Optimization

### Problem
Generic prompts produce mediocre results.

### Solution
Iteratively improve prompts using LLM feedback.

```python
import gepa

# Define seed prompt
seed_prompt = {
    "system_prompt": "You are a helpful assistant. Answer the question."
}

# Define evaluation metric
def evaluate_prompt(candidate):
    # Test on examples
    score = test_on_examples(candidate["system_prompt"])
    return score

# Optimize
result = gepa.optimize(
    seed_candidate=seed_prompt,
    evaluator=evaluate_prompt,
    max_metric_calls=100,
    reflection_lm="openai/gpt-4"
)

print("Optimized prompt:", result.best_candidate["system_prompt"])
```

### Manual Approach (Without GEPA)

```python
def optimize_prompt_manually(
    seed_prompt: str,
    test_cases: list[dict],
    reflection_model: str = "gpt-4"
) -> str:
    """Manual prompt optimization using reflection."""
    
    current_prompt = seed_prompt
    best_score = 0
    
    for iteration in range(10):
        # Execute
        results = run_prompt(current_prompt, test_cases)
        failures = [r for r in results if not r["passed"]]
        
        if not failures:
            break
        
        # Reflect
        reflection = reflect_on_failures(current_prompt, failures)
        
        # Mutate
        new_prompt = generate_improved_prompt(
            current_prompt, 
            reflection
        )
        
        # Evaluate
        new_score = evaluate_prompt(new_prompt, test_cases)
        
        if new_score > best_score:
            current_prompt = new_prompt
            best_score = new_score
    
    return current_prompt

def reflect_on_failures(prompt: str, failures: list) -> str:
    """Use LLM to analyze failures and suggest improvements."""
    
    failure_summary = "\n".join([
        f"Input: {f['input']}\nExpected: {f['expected']}\nGot: {f['actual']}"
        for f in failures[:5]  # Limit to 5 examples
    ])
    
    reflection_prompt = f"""Analyze why this prompt failed on these examples:

PROMPT:
{prompt}

FAILURES:
{failure_summary}

What went wrong? How can the prompt be improved? Be specific."""
    
    return call_llm(reflection_prompt)

def generate_improved_prompt(prompt: str, reflection: str) -> str:
    """Generate improved prompt based on reflection."""
    
    improvement_prompt = f"""Improve this prompt based on the reflection:

CURRENT PROMPT:
{prompt}

REFLECTION:
{reflection}

Generate an improved version of the prompt. Only output the new prompt."""
    
    return call_llm(improvement_prompt)
```

---

## Pattern 2: Code Optimization

### Problem
Code works but is slow, verbose, or inelegant.

### Solution
Use AI to analyze and improve code iteratively.

```python
def optimize_code(
    code: str,
    metric: callable,
    max_iterations: int = 5
) -> str:
    """Optimize code using AI reflection."""
    
    current_code = code
    best_score = metric(code)
    
    for i in range(max_iterations):
        # Get execution trace
        trace = execute_and_trace(current_code)
        
        # Reflect on performance
        reflection = reflect_on_code(current_code, trace)
        
        # Generate improved version
        new_code = improve_code(current_code, reflection)
        
        # Evaluate
        new_score = metric(new_code)
        
        if new_score > best_score:
            current_code = new_code
            best_score = new_score
    
    return current_code

def reflect_on_code(code: str, trace: dict) -> str:
    """Analyze code execution and suggest improvements."""
    
    reflection_prompt = f"""Analyze this code execution:

CODE:
```python
{code}
```

EXECUTION TRACE:
- Time: {trace['time']}s
- Memory: {trace['memory']}MB
- Errors: {trace['errors']}
- Slow paths: {trace['slow_paths']}

Suggest specific improvements for performance, readability, and correctness."""
    
    return call_llm(reflection_prompt)
```

---

## Pattern 3: Configuration Optimization

### Problem
Finding optimal configuration parameters is tedious.

### Solution
Evolutionary search with AI-guided mutations.

```python
def optimize_config(
    seed_config: dict,
    evaluate: callable,
    param_ranges: dict,
    generations: int = 10
) -> dict:
    """Optimize configuration using evolutionary search."""
    
    population = [seed_config]
    
    for gen in range(generations):
        # Evaluate all candidates
        scored = [(config, evaluate(config)) for config in population]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Select top performers
        survivors = [config for config, _ in scored[:5]]
        
        # Generate mutations
        new_candidates = []
        for config in survivors:
            for _ in range(3):
                mutated = mutate_config(config, param_ranges)
                new_candidates.append(mutated)
        
        # Add cross-over candidates
        for i in range(len(survivors) - 1):
            crossover = crossover_configs(
                survivors[i], 
                survivors[i+1]
            )
            new_candidates.append(crossover)
        
        population = survivors + new_candidates
    
    # Return best
    best = max(population, key=evaluate)
    return best

def mutate_config(config: dict, ranges: dict) -> dict:
    """AI-guided mutation of configuration."""
    
    mutation_prompt = f"""Suggest a mutation for this configuration:

CURRENT CONFIG:
{config}

PARAMETER RANGES:
{ranges}

What parameter should change? By how much? Return JSON."""
    
    mutation = call_llm(mutation_prompt)
    return apply_mutation(config, mutation)
```

---

## Pattern 4: Agent Architecture Discovery

### Problem
Finding the best agent architecture is manual and slow.

### Solution
Evolve agent architectures using performance feedback.

```python
def discover_agent_architecture(
    task: str,
    available_tools: list,
    metric: callable,
    generations: int = 5
) -> dict:
    """Discover optimal agent architecture."""
    
    # Start with simple architecture
    seed = {
        "name": "basic_agent",
        "prompt": "You are a helpful assistant.",
        "tools": ["search", "calculate"],
        "strategy": "sequential"
    }
    
    population = [seed]
    
    for gen in range(generations):
        # Evaluate
        scored = [(arch, evaluate_architecture(arch, task, metric)) 
                  for arch in population]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Select top
        survivors = [arch for arch, _ in scored[:3]]
        
        # Evolve
        new_architectures = []
        for arch in survivors:
            # Mutate prompt
            new_arch = arch.copy()
            new_arch["prompt"] = improve_agent_prompt(arch["prompt"], task)
            
            # Mutate tools
            if len(available_tools) > len(arch["tools"]):
                new_tools = suggest_tools(arch, task, available_tools)
                new_arch["tools"] = new_tools
            
            # Mutate strategy
            new_arch["strategy"] = suggest_strategy(arch, task)
            
            new_architectures.append(new_arch)
        
        population = survivors + new_architectures
    
    return max(population, key=lambda arch: evaluate_architecture(arch, task, metric))
```

---

## Actionable Side Information (ASI)

Key concept from GEPA: diagnostic feedback that serves as the text-optimization analogue of a gradient.

```python
def evaluate_withASI(candidate: str, test_case: dict) -> tuple[float, str]:
    """Evaluate candidate with actionable side information."""
    
    try:
        result = run_candidate(candidate, test_case["input"])
        
        if result == test_case["expected"]:
            return 1.0, "Success"
        
        # Generate actionable feedback
        asi = f"""
Expected: {test_case['expected']}
Got: {result}
Difference: {analyze_difference(result, test_case['expected'])}
Suggestion: {generate_fix_suggestion(candidate, result, test_case['expected'])}
"""
        return 0.0, asi
    
    except Exception as e:
        return -1.0, f"Error: {str(e)}"
```

---

## Decision Tree: Which Optimization Pattern?

```
START
  │
  ├─ What are you optimizing?
  │   ├─ System prompt → Prompt Optimization
  │   ├─ Code quality → Code Optimization
  │   ├─ Configuration → Config Optimization
  │   └─ Agent behavior → Architecture Discovery
  │
  ├─ What's your evaluation metric?
  │   ├─ Accuracy → Use test cases
  │   ├─ Performance → Measure execution time/memory
  │   ├─ Readability → Use code review scoring
  │   └─ Cost → Track token usage/API calls
  │
  └─ How many iterations?
      ├─ <5 → Manual reflection
      ├─ 5-50 → Semi-automated loop
      └─ >50 → Full evolutionary search (GEPA)
```

---

## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Optimizing without metrics | Can't measure improvement |
| Too many parameters | Search space too large |
| No validation set | Overfitting to training examples |
| Ignoring cost | Optimization itself costs tokens |
| Premature convergence | Stopping too early |
| Random mutations | Uninformed search |

---

## Integration with Skills

### ai-regression-testing
- Use optimization to improve test generation
- Optimize test prompts for better coverage

### clean-code
- Optimize code for readability
- Find better naming and structure

### design-patterns
- Discover when to apply patterns
- Optimize pattern selection

### humanizer
- Optimize prompts to reduce AI slop
- Find better ways to sound natural

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────┐
│                 OPTIMIZATION PATTERNS                        │
├─────────────────────────────────────────────────────────────┤
│ Prompt         → Iterative refinement with reflection       │
│ Code           → Execute, trace, reflect, improve           │
│ Configuration  → Evolutionary search with AI mutations      │
│ Architecture   → Evolve tools, prompts, strategies          │
├─────────────────────────────────────────────────────────────┤
│ KEY CONCEPT: Actionable Side Information (ASI)              │
│ - Not just "failed" but WHY it failed                       │
│ - Diagnostic feedback as gradient analogue                  │
│ - Enables targeted improvements                             │
└─────────────────────────────────────────────────────────────┘
```

---

## References

- GEPA (Genetic-Pareto): https://github.com/gepa-ai/gepa
- DSPy: https://dspy.ai/
- Reflective Prompt Optimization: https://arxiv.org/abs/2507.19457
- OpenAI Cookbook - Self-Evolving Agents: https://cookbook.openai.com/examples/partners/self_evolving_agents/autonomous_agent_retraining
