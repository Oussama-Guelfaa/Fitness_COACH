import SwiftUI
import HealthKit
import Foundation
import UIKit

@main
struct FitnessCoachHealthCompanionApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    @StateObject private var syncService = HealthKitSyncService()
    @State private var apiBaseURL = "https://your-railway-domain.up.railway.app"
    @State private var linkCode = ""
    @State private var status = "Not connected"

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("API base URL", text: $apiBaseURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                }

                Section("Pairing") {
                    TextField("Telegram /health_link code", text: $linkCode)
                        .textInputAutocapitalization(.characters)
                    Button("Connect Apple Health") {
                        Task {
                            do {
                                try await syncService.requestAuthorization()
                                try await syncService.claimLinkCode(
                                    apiBaseURL: apiBaseURL,
                                    linkCode: linkCode
                                )
                                status = "Connected"
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                }

                Section("Sync") {
                    Button("Sync Last 14 Days") {
                        Task {
                            do {
                                let result = try await syncService.syncLastDays(
                                    apiBaseURL: apiBaseURL,
                                    days: 14
                                )
                                status = "Synced \(result.dailySummaries) summaries and \(result.workouts) workouts"
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                }

                Section("Status") {
                    Text(status)
                }
            }
            .navigationTitle("Fitness Coach Health")
        }
    }
}

final class HealthKitSyncService: ObservableObject {
    private let healthStore = HKHealthStore()
    private let tokenKey = "fitnessCoachAppleHealthSyncToken"

    private var readTypes: Set<HKObjectType> {
        var types: Set<HKObjectType> = [
            HKObjectType.workoutType()
        ]
        [
            HKQuantityTypeIdentifier.stepCount,
            .activeEnergyBurned,
            .restingHeartRate,
            .heartRateVariabilitySDNN,
            .distanceWalkingRunning,
            .vo2Max,
            .bodyMass
        ].compactMap { HKObjectType.quantityType(forIdentifier: $0) }
            .forEach { types.insert($0) }

        if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) {
            types.insert(sleep)
        }
        return types
    }

    func requestAuthorization() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw CompanionError.healthKitUnavailable
        }
        try await withCheckedThrowingContinuation { continuation in
            healthStore.requestAuthorization(toShare: [], read: readTypes) { success, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if success {
                    continuation.resume()
                } else {
                    continuation.resume(throwing: CompanionError.authorizationDenied)
                }
            }
        }
    }

    func claimLinkCode(apiBaseURL: String, linkCode: String) async throws {
        let request = ClaimRequest(
            linkCode: linkCode,
            deviceName: UIDevice.current.name,
            permissions: HealthPermission.defaultIdentifiers
        )
        let response: ClaimResponse = try await APIClient.post(
            baseURL: apiBaseURL,
            path: "/api/apple-health/claim",
            body: request,
            bearerToken: nil
        )
        UserDefaults.standard.set(response.syncToken, forKey: tokenKey)
    }

    func syncLastDays(apiBaseURL: String, days: Int) async throws -> SyncResponse {
        guard let token = UserDefaults.standard.string(forKey: tokenKey), !token.isEmpty else {
            throw CompanionError.missingSyncToken
        }

        let calendar = Calendar.current
        let endDate = Date()
        guard let startDate = calendar.date(byAdding: .day, value: -days + 1, to: calendar.startOfDay(for: endDate)) else {
            throw CompanionError.invalidDateRange
        }

        let summaries = try await fetchDailySummaries(from: startDate, to: endDate)
        let workouts = try await fetchWorkouts(from: startDate, to: endDate)
        let payload = SyncRequest(
            permissions: HealthPermission.defaultIdentifiers,
            dailySummaries: summaries,
            workouts: workouts
        )
        return try await APIClient.post(
            baseURL: apiBaseURL,
            path: "/api/apple-health/sync",
            body: payload,
            bearerToken: token
        )
    }

    private func fetchDailySummaries(from startDate: Date, to endDate: Date) async throws -> [DailySummaryPayload] {
        let calendar = Calendar.current
        var summaries: [DailySummaryPayload] = []
        var current = calendar.startOfDay(for: startDate)

        while current <= endDate {
            guard let next = calendar.date(byAdding: .day, value: 1, to: current) else { break }
            async let steps = sumQuantity(.stepCount, from: current, to: next, unit: .count())
            async let activeEnergy = sumQuantity(.activeEnergyBurned, from: current, to: next, unit: .kilocalorie())
            async let distance = sumQuantity(.distanceWalkingRunning, from: current, to: next, unit: .meterUnit(with: .kilo))
            async let restingHR = averageQuantity(.restingHeartRate, from: current, to: next, unit: HKUnit.count().unitDivided(by: .minute()))
            async let hrv = averageQuantity(.heartRateVariabilitySDNN, from: current, to: next, unit: .secondUnit(with: .milli))
            async let vo2Max = averageQuantity(.vo2Max, from: current, to: next, unit: HKUnit(from: "ml/kg*min"))
            async let bodyMass = averageQuantity(.bodyMass, from: current, to: next, unit: .gramUnit(with: .kilo))
            async let sleepValue = sleepMinutes(from: current, to: next)
            async let workoutValue = workoutMinutes(from: current, to: next)

            summaries.append(
                DailySummaryPayload(
                    summaryDate: DateFormatter.apiDate.string(from: current),
                    steps: Int((try await steps) ?? 0),
                    activeEnergyKcal: try await activeEnergy,
                    restingHeartRateBpm: try await restingHR,
                    hrvMs: try await hrv,
                    sleepMinutes: try await sleepValue,
                    workoutMinutes: Int((try await workoutValue) ?? 0),
                    walkingRunningDistanceKm: try await distance,
                    vo2Max: try await vo2Max,
                    bodyMassKg: try await bodyMass
                )
            )
            current = next
        }
        return summaries
    }

    private func fetchWorkouts(from startDate: Date, to endDate: Date) async throws -> [WorkoutPayload] {
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: HKObjectType.workoutType(),
                predicate: predicate,
                limit: HKObjectQueryNoLimit,
                sortDescriptors: [NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: true)]
            ) { _, samples, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                let workouts = (samples as? [HKWorkout] ?? []).map { workout in
                    WorkoutPayload(
                        externalUuid: workout.uuid.uuidString,
                        workoutType: workout.workoutActivityType.fitnessCoachName,
                        startedAt: DateFormatter.apiDateTime.string(from: workout.startDate),
                        endedAt: DateFormatter.apiDateTime.string(from: workout.endDate),
                        durationMinutes: workout.duration / 60,
                        activeEnergyKcal: workout.totalEnergyBurned?.doubleValue(for: .kilocalorie()),
                        distanceKm: workout.totalDistance?.doubleValue(for: .meterUnit(with: .kilo))
                    )
                }
                continuation.resume(returning: workouts)
            }
            healthStore.execute(query)
        }
    }

    private func sumQuantity(
        _ identifier: HKQuantityTypeIdentifier,
        from startDate: Date,
        to endDate: Date,
        unit: HKUnit
    ) async throws -> Double? {
        try await statisticsQuantity(identifier, from: startDate, to: endDate, unit: unit, options: .cumulativeSum)
    }

    private func averageQuantity(
        _ identifier: HKQuantityTypeIdentifier,
        from startDate: Date,
        to endDate: Date,
        unit: HKUnit
    ) async throws -> Double? {
        try await statisticsQuantity(identifier, from: startDate, to: endDate, unit: unit, options: .discreteAverage)
    }

    private func statisticsQuantity(
        _ identifier: HKQuantityTypeIdentifier,
        from startDate: Date,
        to endDate: Date,
        unit: HKUnit,
        options: HKStatisticsOptions
    ) async throws -> Double? {
        guard let quantityType = HKQuantityType.quantityType(forIdentifier: identifier) else { return nil }
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        return try await withCheckedThrowingContinuation { continuation in
            let query = HKStatisticsQuery(quantityType: quantityType, quantitySamplePredicate: predicate, options: options) { _, stats, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                let quantity = options == .cumulativeSum ? stats?.sumQuantity() : stats?.averageQuantity()
                continuation.resume(returning: quantity?.doubleValue(for: unit))
            }
            healthStore.execute(query)
        }
    }

    private func sleepMinutes(from startDate: Date, to endDate: Date) async throws -> Int? {
        guard let sleepType = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) else { return nil }
        let predicate = HKQuery.predicateForSamples(withStart: startDate, end: endDate)
        return try await withCheckedThrowingContinuation { continuation in
            let query = HKSampleQuery(sampleType: sleepType, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                let asleepValues: Set<Int> = [
                    HKCategoryValueSleepAnalysis.asleepCore.rawValue,
                    HKCategoryValueSleepAnalysis.asleepDeep.rawValue,
                    HKCategoryValueSleepAnalysis.asleepREM.rawValue,
                    HKCategoryValueSleepAnalysis.asleepUnspecified.rawValue
                ]
                let seconds = (samples as? [HKCategorySample] ?? [])
                    .filter { asleepValues.contains($0.value) }
                    .reduce(0.0) { $0 + $1.endDate.timeIntervalSince($1.startDate) }
                continuation.resume(returning: Int(seconds / 60))
            }
            healthStore.execute(query)
        }
    }

    private func workoutMinutes(from startDate: Date, to endDate: Date) async throws -> Double? {
        let workouts = try await fetchWorkouts(from: startDate, to: endDate)
        return workouts.reduce(0.0) { $0 + ($1.durationMinutes ?? 0) }
    }
}

enum APIClient {
    static func post<RequestBody: Encodable, ResponseBody: Decodable>(
        baseURL: String,
        path: String,
        body: RequestBody,
        bearerToken: String?
    ) async throws -> ResponseBody {
        guard let url = URL(string: baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path) else {
            throw CompanionError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let bearerToken {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try JSONEncoder.api.encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200..<300).contains(httpResponse.statusCode) else {
            throw CompanionError.requestFailed(String(data: data, encoding: .utf8) ?? "Request failed")
        }
        return try JSONDecoder.api.decode(ResponseBody.self, from: data)
    }
}

struct ClaimRequest: Encodable {
    let linkCode: String
    let deviceName: String
    let permissions: [String]

    enum CodingKeys: String, CodingKey {
        case linkCode = "link_code"
        case deviceName = "device_name"
        case permissions
    }
}

struct ClaimResponse: Decodable {
    let syncToken: String

    enum CodingKeys: String, CodingKey {
        case syncToken = "sync_token"
    }
}

struct SyncRequest: Encodable {
    let permissions: [String]
    let dailySummaries: [DailySummaryPayload]
    let workouts: [WorkoutPayload]

    enum CodingKeys: String, CodingKey {
        case permissions
        case dailySummaries = "daily_summaries"
        case workouts
    }
}

struct SyncResponse: Decodable {
    let synced: Bool
    let dailySummaries: Int
    let workouts: Int

    enum CodingKeys: String, CodingKey {
        case synced
        case dailySummaries = "daily_summaries"
        case workouts
    }
}

struct DailySummaryPayload: Encodable {
    let summaryDate: String
    let steps: Int?
    let activeEnergyKcal: Double?
    let restingHeartRateBpm: Double?
    let hrvMs: Double?
    let sleepMinutes: Int?
    let workoutMinutes: Int?
    let walkingRunningDistanceKm: Double?
    let vo2Max: Double?
    let bodyMassKg: Double?

    enum CodingKeys: String, CodingKey {
        case summaryDate = "summary_date"
        case steps
        case activeEnergyKcal = "active_energy_kcal"
        case restingHeartRateBpm = "resting_heart_rate_bpm"
        case hrvMs = "hrv_ms"
        case sleepMinutes = "sleep_minutes"
        case workoutMinutes = "workout_minutes"
        case walkingRunningDistanceKm = "walking_running_distance_km"
        case vo2Max = "vo2_max"
        case bodyMassKg = "body_mass_kg"
    }
}

struct WorkoutPayload: Encodable {
    let externalUuid: String
    let workoutType: String
    let startedAt: String
    let endedAt: String
    let durationMinutes: Double?
    let activeEnergyKcal: Double?
    let distanceKm: Double?

    enum CodingKeys: String, CodingKey {
        case externalUuid = "external_uuid"
        case workoutType = "workout_type"
        case startedAt = "started_at"
        case endedAt = "ended_at"
        case durationMinutes = "duration_minutes"
        case activeEnergyKcal = "active_energy_kcal"
        case distanceKm = "distance_km"
    }
}

enum HealthPermission {
    static let defaultIdentifiers = [
        "stepCount",
        "activeEnergyBurned",
        "restingHeartRate",
        "heartRateVariabilitySDNN",
        "sleepAnalysis",
        "workouts",
        "distanceWalkingRunning",
        "vo2Max",
        "bodyMass"
    ]
}

enum CompanionError: LocalizedError {
    case healthKitUnavailable
    case authorizationDenied
    case missingSyncToken
    case invalidDateRange
    case invalidURL
    case requestFailed(String)

    var errorDescription: String? {
        switch self {
        case .healthKitUnavailable:
            return "HealthKit is unavailable on this device."
        case .authorizationDenied:
            return "Apple Health authorization was denied."
        case .missingSyncToken:
            return "Connect with a /health_link code before syncing."
        case .invalidDateRange:
            return "Invalid sync date range."
        case .invalidURL:
            return "Invalid API URL."
        case .requestFailed(let message):
            return message
        }
    }
}

extension JSONEncoder {
    static var api: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .useDefaultKeys
        return encoder
    }
}

extension JSONDecoder {
    static var api: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .useDefaultKeys
        return decoder
    }
}

extension DateFormatter {
    static let apiDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    static let apiDateTime: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

extension HKWorkoutActivityType {
    var fitnessCoachName: String {
        switch self {
        case .running: return "running"
        case .walking: return "walking"
        case .cycling: return "cycling"
        case .traditionalStrengthTraining: return "strength_training"
        case .functionalStrengthTraining: return "functional_strength_training"
        case .highIntensityIntervalTraining: return "hiit"
        case .swimming: return "swimming"
        case .yoga: return "yoga"
        default: return "other"
        }
    }
}
