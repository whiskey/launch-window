import Foundation

// PROOF OF CONCEPT — a Swift port of `firmware/lib/sky.py`.
//
// The beacon computes tonight. To say anything about the nights after it, this
// client has to compute the sky itself, which means a second implementation of
// the one thing the project says must never be wrong. That is a real cost and
// it is taken deliberately, with one mitigation that makes it bearable: this
// engine also computes *tonight*, where the beacon's own answer is available to
// check it against. See `OutlookEngine.selfCheck`.
//
// The port is deliberately line-for-line rather than idiomatic. Every constant,
// every series term and the crossing search are the same as in `sky.py`, so the
// two can be read side by side and diffed by eye when either changes.
//
// One thing is kept that this platform does not need: the pre-split mean-motion
// rates. On the RP2040 they are the single most important detail in the file —
// a float32 cannot hold `360.98564736629` well enough to survive nine thousand
// days of multiplication, and getting it wrong moved every rise and set time by
// five minutes while every host test still passed. Here, in double precision,
// plain constants would work. They are split anyway so that this file and its
// original stay comparable; a divergence should be a real difference, never a
// difference in how the arithmetic was arranged.

enum SkyMath {
    /// J2000.0 (2000-01-01 12:00 UTC) as a Unix timestamp.
    static let j2000Unix = 946_728_000
    private static let earthRadiusKm = 6378.14

    // Mean motions in degrees per day, pre-split into (whole, remainder).
    private static let sunMeanLonRate = (0.0, 0.9856474)
    private static let sunMeanAnomRate = (0.0, 0.9856003)
    private static let gmstRate = (360.0, 0.98564736629)
    private static let moonMeanLonRate = (13.0, 0.176396475)
    private static let moonAnomRate = (13.0, 0.064992950)
    private static let elongationRate = (12.0, 0.190749114)
    private static let argLatRate = (13.0, 0.229350240)
    private static let moonSunAnomRate = (0.0, 0.985600282)

    /// The Sun's upper limb at rise and set: refraction at the horizon plus the
    /// solar semi-diameter. Twilight is geometric and takes no refraction.
    static let sunriseAltitude = -0.833
    static let civilAltitude = -6.0
    static let nauticalAltitude = -12.0
    static let astronomicalAltitude = -18.0

    /// Time since J2000 as whole days and a fraction of a day.
    static func epochSplit(_ timestamp: Int) -> (days: Double, fraction: Double) {
        let seconds = timestamp - j2000Unix
        // Python's divmod floors towards negative infinity; Swift's / truncates.
        var days = seconds / 86400
        var remainder = seconds % 86400
        if remainder < 0 {
            days -= 1
            remainder += 86400
        }
        return (Double(days), Double(remainder) / 86400.0)
    }

    /// `constant + rate * (days + fraction)` in degrees, reduced mod 360.
    private static func angle(_ constant: Double,
                              _ rate: (Double, Double),
                              _ days: Double,
                              _ fraction: Double) -> Double {
        let (whole, remainder) = rate
        let value = constant
            + (whole * days).truncatingRemainder(dividingBy: 360)
            + (remainder * days).truncatingRemainder(dividingBy: 360)
            + whole * fraction
            + remainder * fraction
        return value.positiveRemainder(360)
    }

    /// Greenwich mean sidereal time in degrees (IAU 1982).
    static func gmstDegrees(days: Double, fraction: Double) -> Double {
        angle(280.46061837, gmstRate, days, fraction)
    }

    private static func obliquity(days: Double) -> Double {
        (23.439 - 0.0000004 * days) * .pi / 180
    }

    /// Geocentric right ascension and declination of the Sun, in radians.
    static func sunEquatorial(days: Double, fraction: Double) -> (ra: Double, dec: Double) {
        let meanLon = angle(280.460, sunMeanLonRate, days, fraction)
        let meanAnom = angle(357.528, sunMeanAnomRate, days, fraction) * .pi / 180
        let eclipticLon = (meanLon + 1.915 * sin(meanAnom) + 0.020 * sin(2 * meanAnom)) * .pi / 180
        let obl = obliquity(days: days)
        let ra = atan2(cos(obl) * sin(eclipticLon), cos(eclipticLon))
        let dec = asin(sin(obl) * sin(eclipticLon))
        return (ra, dec)
    }

    /// Geocentric ecliptic longitude, latitude (radians) and distance (km).
    ///
    /// The truncated ELP series from Meeus chapter 47, keeping terms above
    /// roughly 0.1 degrees. The T² and T³ corrections are dropped: they are
    /// worth 0.0006 degrees at this epoch and would matter for a century, not
    /// for a decade.
    static func moonEcliptic(days: Double,
                             fraction: Double) -> (lon: Double, lat: Double, distance: Double) {
        let meanLon = angle(218.3164477, moonMeanLonRate, days, fraction)
        let sunAnom = angle(357.5291092, moonSunAnomRate, days, fraction) * .pi / 180
        let moonAnom = angle(134.9633964, moonAnomRate, days, fraction) * .pi / 180
        let elongation = angle(297.8501921, elongationRate, days, fraction) * .pi / 180
        let argLat = angle(93.2720950, argLatRate, days, fraction) * .pi / 180

        let lon = meanLon + (
            6.289 * sin(moonAnom)
            + 1.274 * sin(2 * elongation - moonAnom)
            + 0.658 * sin(2 * elongation)
            + 0.214 * sin(2 * moonAnom)
            - 0.186 * sin(sunAnom)
            - 0.114 * sin(2 * argLat)
        )
        let lat = 5.128 * sin(argLat)
            + 0.281 * sin(moonAnom + argLat)
            - 0.278 * sin(argLat - moonAnom)
            - 0.173 * sin(2 * elongation - argLat)
        let distance = 385001.0
            - 20905.0 * cos(moonAnom)
            - 3699.0 * cos(2 * elongation - moonAnom)
            - 2956.0 * cos(2 * elongation)
            - 570.0 * cos(2 * moonAnom)
        return (lon.positiveRemainder(360) * .pi / 180, lat * .pi / 180, distance)
    }

    private static func eclipticToEquatorial(lon: Double,
                                             lat: Double,
                                             days: Double) -> (ra: Double, dec: Double) {
        let obl = obliquity(days: days)
        let ra = atan2(sin(lon) * cos(obl) - tan(lat) * sin(obl), cos(lon))
        let dec = asin(sin(lat) * cos(obl) + cos(lat) * sin(obl) * sin(lon))
        return (ra, dec)
    }

    /// Azimuth is measured from north, eastwards.
    private static func toHorizontal(ra: Double, dec: Double,
                                     days: Double, fraction: Double,
                                     latitude: Double, longitude: Double) -> (alt: Double, az: Double) {
        let lst = (gmstDegrees(days: days, fraction: fraction) + longitude)
            .positiveRemainder(360) * .pi / 180
        let hourAngle = lst - ra
        let lat = latitude * .pi / 180
        let sinAlt = sin(lat) * sin(dec) + cos(lat) * cos(dec) * cos(hourAngle)
        let alt = asin(min(1.0, max(-1.0, sinAlt)))
        let az = atan2(-cos(dec) * sin(hourAngle),
                       cos(lat) * sin(dec) - sin(lat) * cos(dec) * cos(hourAngle))
        return (alt * 180 / .pi, (az * 180 / .pi).positiveRemainder(360))
    }

    static func sunAltitude(at timestamp: Int, latitude: Double, longitude: Double) -> Double {
        let (days, fraction) = epochSplit(timestamp)
        let (ra, dec) = sunEquatorial(days: days, fraction: fraction)
        return toHorizontal(ra: ra, dec: dec, days: days, fraction: fraction,
                            latitude: latitude, longitude: longitude).alt
    }

    /// Topocentric altitude of the Moon.
    ///
    /// The horizontal-parallax correction is what turns a geocentric altitude
    /// into one an observer would measure — up to a degree, and the difference
    /// between "already set" and "still washing out the target".
    static func moonAltitude(at timestamp: Int, latitude: Double, longitude: Double) -> Double {
        let (days, fraction) = epochSplit(timestamp)
        let (lon, lat, distance) = moonEcliptic(days: days, fraction: fraction)
        let (ra, dec) = eclipticToEquatorial(lon: lon, lat: lat, days: days)
        let (alt, _) = toHorizontal(ra: ra, dec: dec, days: days, fraction: fraction,
                                    latitude: latitude, longitude: longitude)
        let parallax = asin(earthRadiusKm / distance) * 180 / .pi
        return alt - parallax * cos(alt * .pi / 180)
    }

    /// Illuminated fraction of the Moon's disc, 0 (new) to 1 (full).
    static func moonIllumination(at timestamp: Int) -> Double {
        let (days, fraction) = epochSplit(timestamp)
        let (moonLon, moonLat, _) = moonEcliptic(days: days, fraction: fraction)
        let (sunRA, sunDec) = sunEquatorial(days: days, fraction: fraction)
        let (moonRA, moonDec) = eclipticToEquatorial(lon: moonLon, lat: moonLat, days: days)
        let cosElongation = sin(sunDec) * sin(moonDec)
            + cos(sunDec) * cos(moonDec) * cos(sunRA - moonRA)
        let elongation = acos(min(1.0, max(-1.0, cosElongation)))
        // The Sun's distance dwarfs the Moon's, so the phase angle is the
        // supplement of the elongation to well within this module's accuracy.
        return (1.0 + cos(.pi - elongation)) / 2.0
    }

    static let synodicMonth = 29.530588853
    /// Reference new moon, 2000-01-06 18:14 UTC, as days since J2000.
    private static let newMoonEpochDays = 5.2597

    static func moonAgeDays(at timestamp: Int) -> Double {
        let (days, fraction) = epochSplit(timestamp)
        return (days + fraction - newMoonEpochDays).positiveRemainder(synodicMonth)
    }

    static let phaseNames = ["new", "waxing crescent", "first quarter", "waxing gibbous",
                             "full", "waning gibbous", "last quarter", "waning crescent"]

    /// Named from the age in the synodic cycle rather than from the illuminated
    /// fraction, because illumination alone cannot tell waxing from waning.
    static func moonPhaseName(at timestamp: Int) -> String {
        let index = Int((moonAgeDays(at: timestamp) / synodicMonth) * 8 + 0.5) % 8
        return phaseNames[index]
    }

    /// Times in `[start, end)` where an altitude crosses `target`.
    ///
    /// Coarse sampling then integer bisection to one second. Sampling rather
    /// than a closed form because closed forms need special cases for bodies
    /// that never rise and never set, and sampling degrades into "no crossing
    /// found" without any of them.
    static func crossings(altitude: (Int) -> Double,
                          from start: Int, to end: Int,
                          target: Double, step: Int = 300) -> [(timestamp: Int, rising: Bool)] {
        var found: [(Int, Bool)] = []
        var previousTimestamp = start
        var previous = altitude(start) - target
        var timestamp = start + step
        while timestamp <= end {
            let current = altitude(timestamp) - target
            if (previous < 0) != (current < 0) {
                var low = previousTimestamp
                var high = timestamp
                var lowValue = previous
                while high - low > 1 {
                    let middle = (low + high) / 2
                    let middleValue = altitude(middle) - target
                    if (lowValue < 0) != (middleValue < 0) {
                        high = middle
                    } else {
                        low = middle
                        lowValue = middleValue
                    }
                }
                found.append((high, current > 0))
            }
            previousTimestamp = timestamp
            previous = current
            timestamp += step
        }
        return found
    }

    private static func first(_ events: [(timestamp: Int, rising: Bool)],
                              rising: Bool) -> Int? {
        events.first { $0.rising == rising }?.timestamp
    }

    /// The boundaries of one night, as Unix timestamps.
    ///
    /// Any boundary the Sun does not reach is nil rather than a guess. At 52
    /// degrees north astronomical night genuinely does not exist for weeks
    /// around midsummer, and inventing one would be lying about the only thing
    /// this can compute exactly.
    struct Night: Sendable, Hashable {
        var sunset: Int?
        var sunrise: Int?
        var duskAstronomical: Int?
        var dawnAstronomical: Int?
        var duskNautical: Int?
        var dawnNautical: Int?
        var darkSeconds: Int = 0
    }

    /// - Parameter timestamp: the window starts 12 hours earlier, so calling
    ///   this in the afternoon describes tonight and calling it at 03:00 still
    ///   describes the night in progress rather than skipping to the next one.
    static func night(at timestamp: Int, latitude: Double, longitude: Double) -> Night {
        func sunAlt(_ t: Int) -> Double {
            sunAltitude(at: t, latitude: latitude, longitude: longitude)
        }
        let start = timestamp - 12 * 3600
        let end = timestamp + 24 * 3600

        let sunEvents = crossings(altitude: sunAlt, from: start, to: end, target: sunriseAltitude)
        let darkEvents = crossings(altitude: sunAlt, from: start, to: end, target: astronomicalAltitude)
        let nauticalEvents = crossings(altitude: sunAlt, from: start, to: end, target: nauticalAltitude)

        var result = Night()
        result.sunset = first(sunEvents, rising: false)
        result.duskAstronomical = first(darkEvents, rising: false)
        result.duskNautical = first(nauticalEvents, rising: false)

        if let sunset = result.sunset {
            result.sunrise = first(sunEvents.filter { $0.timestamp > sunset }, rising: true)
        }
        if let dusk = result.duskAstronomical {
            result.dawnAstronomical = first(darkEvents.filter { $0.timestamp > dusk }, rising: true)
            if let dawn = result.dawnAstronomical {
                result.darkSeconds = dawn - dusk
            }
        }
        if let nauticalDusk = result.duskNautical {
            result.dawnNautical = first(nauticalEvents.filter { $0.timestamp > nauticalDusk },
                                        rising: true)
        }
        return result
    }

    /// Moonrise and moonset within a window, either of which may be nil.
    static func moonEvents(from start: Int, to end: Int,
                           latitude: Double, longitude: Double) -> (rise: Int?, set: Int?) {
        func moonAlt(_ t: Int) -> Double {
            moonAltitude(at: t, latitude: latitude, longitude: longitude)
        }
        let events = crossings(altitude: moonAlt, from: start, to: end, target: 0.0)
        return (first(events, rising: true), first(events, rising: false))
    }
}

private extension Double {
    /// Python's `%`, which follows the sign of the divisor. Swift's
    /// `truncatingRemainder` follows the dividend, and the difference is a
    /// negative angle where the original has a positive one.
    func positiveRemainder(_ divisor: Double) -> Double {
        let remainder = truncatingRemainder(dividingBy: divisor)
        return remainder < 0 ? remainder + divisor : remainder
    }
}
