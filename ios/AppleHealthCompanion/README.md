# Apple Health Companion

This folder contains the minimal Swift source needed for an iOS companion app
that reads Apple Health with explicit user permission and syncs summaries to the
Fitness Coach backend.

Required Xcode setup:

- Create a new iOS SwiftUI app.
- Enable the HealthKit capability on the app target.
- Add `NSHealthShareUsageDescription` to `Info.plist`.
- Copy `FitnessCoachHealthCompanion.swift` into the app target.
- Run on a real iPhone. HealthKit is not useful on a plain server backend.

Runtime flow:

1. In Telegram or CLI, run `/health_link`.
2. Paste the generated code into the iOS app.
3. The app calls `POST /api/apple-health/claim` and stores the returned sync token.
4. The app reads HealthKit data locally.
5. The app calls `POST /api/apple-health/sync` with the bearer sync token.

The backend stores daily summaries and workouts, then injects them into the
LangGraph coach state.
