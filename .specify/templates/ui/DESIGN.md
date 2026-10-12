# CommerceAgent UI Design System

## Design Goal

CommerceAgent UI should present an enterprise AI Agent platform.

The design should communicate:

User request → Agent reasoning process → Business context → Safety decision → Verified outcome

## Visual Direction

Reference style:

- Linear
- Vercel
- Ant Design Pro
- Agent observability platforms

Avoid:

- Sci-fi AI interfaces
- Excessive animations
- Chatbot style
- Consumer mobile application style

## Layout

Default application layout:

```
Sidebar
+
Header
+
Workspace
```

## Core Pages

- Mission Center
- Run Replay
- Safety Center
- Human Collaboration
- Enterprise Dashboard

## Components

Required reusable components:

- StatusBadge
- RunCard
- Timeline
- EvidencePanel
- SafetyEventCard
- MetricCard

## Status Language

RUNNING: processing

COMPLETED: successful execution

SAFE_STOP: blocked by safety boundary

ESCALATED: requires human handling

FAILED: execution failure

## Visualization

Use:

- React Flow for agent workflow visualization
- ECharts for business metrics
- Ant Design components for enterprise UI

## Principle

The UI should explain why the Agent acted, not only show what happened.
