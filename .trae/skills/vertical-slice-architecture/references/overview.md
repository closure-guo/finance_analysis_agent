# Vertical Slice Architecture: Overview & Core Principles

## What is Vertical Slice Architecture (VSA)

VSA is an architectural style originated by Jimmy Bogard (creator of MediatR and AutoMapper) that organizes code around **features/use cases** rather than technical layers (Controller/Service/Repository). Each "slice" is a self-contained unit that encapsulates all code needed to fulfill a specific request, from the API endpoint down to data access.

> "Minimize coupling between slices, and maximize coupling in a slice." -- Jimmy Bogard

## Core Principles

1. **Couple along the axis of change**: When adding a feature, you typically touch UI, validation, models, and data access. VSA keeps all these in one place instead of scattering them across layers.

2. **Each request is a distinct use case**: Treat commands (POST/PUT/DELETE) and queries (GET) as separate use cases. VSA gives you CQRS naturally.

3. **New features only add code**: You don't change shared code or worry about side effects. Each slice evolves independently.

4. **Tailored approach over one-size-fits-all**: Each slice can choose the best implementation pattern -- one slice can use EF Core, another raw SQL, another stored procedures. No application-wide mandates.

5. **Start simple, refactor when needed**: Begin with Transaction Script. When business logic grows complex, refactor to richer domain patterns (Domain Model, DDD Aggregates, Services).

## VSA vs Layered Architectures

| Aspect | Layered (Clean/Onion/Hex) | Vertical Slice |
|--------|--------------------------|----------------|
| Organization | By technical concern (layers) | By feature/use case |
| Navigation for feature | Jump across multiple folders | All code in one place |
| Adding feature | Touch many layers | Add files to one slice |
| Coupling direction | Cross-layer (DIP) | Vertical within slice |
| Abstractions | Heavy (Repositories, Services, DTOs) | Minimal (shared infra only) |
| Test complexity | Mock-heavy due to abstractions | Test handlers directly |
| Team scaling | Hard (concurrent changes to shared layers) | Easy (independent slices) |
| Learning curve | High (must understand all layers) | Low (local reasoning) |

## VSA and Clean Architecture: Complementary, Not Competing

Both approaches are **complementary strategies** on a spectrum of product maturity:

- **VSA excels tactically**: Rapid feature delivery, minimizing change radius, high developer velocity. Ideal for early-stage products and peripheral modules.
- **Clean Architecture excels strategically**: Long-term domain stability, clear separation of concerns, surviving team changes. Ideal for complex core domains.

**Hybrid approach** (recommended for large systems):
- Use Clean Architecture for the **system core** (domain invariants, shared kernel)
- Use VSA for **peripheral modules** (independent feature delivery)
- Inner layer defines domain rules; outer slices provide implementation variability

> "Both approaches implement different phases of the corporate solution life cycle: vertical slices prevail in early stages providing rapid adaptation; as product and organizational complexity grow, the role of Clean Architecture increases." -- Architecture Weekly

## Natural Affinities

VSA pairs naturally with these patterns:

- **CQRS**: Commands and queries are already separated per slice
- **MediatR**: Library for dispatching requests to handlers
- **REPR Pattern**: Request-Endpoint-Response structure for APIs
- **DDD Bounded Contexts**: Each slice or group of slices maps to a bounded context
- **Domain Events**: For decoupled cross-slice communication
- **Feature Flags**: Deploy code frequently while controlling visibility

## When to Use VSA

**Ideal for:**
- Request-specific logic dominates (most logic is handler-specific)
- Team values code locality and fast navigation
- Want to avoid premature abstractions
- Microservices or modular monoliths
- Teams practicing continuous delivery

**Less ideal for:**
- Complex domain model reused across many entry points (API + message handlers + scheduled jobs)
- Very large enterprise systems with >5 developers per bounded context (consider hybrid)
- Teams unfamiliar with code smells and refactoring (VSA requires judgment)

## Team Prerequisites

VSA assumes your team can:
- Recognize when a handler/service does too much logic
- Know when to push complex logic into domain entities/services
- Apply refactoring techniques (Extract Method, Extract Class, etc.)
- Make localized architecture decisions per feature
