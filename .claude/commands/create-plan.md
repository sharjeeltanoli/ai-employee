# Create Plan Skill

When triggered with a task, create a detailed Plan.md file in /Plans folder.

Plan.md format must be:
```
---
created: [current datetime]
task: [task name]
status: pending
requires_approval: [yes/no]
---

## Objective
[What needs to be done]

## Steps
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

## Approval Required?
[Yes/No - reason based on Company Handbook]
```

After creating plan, update Dashboard.md Active Tasks count.
