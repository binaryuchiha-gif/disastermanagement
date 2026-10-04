// Minimal i18n (English / Tamil / Hindi). Pure JS, node-testable.
export const MESSAGES = {
  en: {
    app_title: "ResQFlow-X",
    safest: "Safest route", fastest: "Fastest route", balanced: "Balanced",
    sos: "SOS", download_map: "Download offline map", high_contrast: "High contrast",
    rainfall: "Rainfall", start_set: "Start set — tap destination",
    outside_network: "Tap is outside the road network", no_route: "No route found",
    sos_queued: "SOS queued (will send when online)",
    why_route: "Why this route",
  },
  ta: {
    app_title: "ரெஸ்க்யூஃப்ளோ-X",
    safest: "பாதுகாப்பான பாதை", fastest: "விரைவான பாதை", balanced: "சமநிலை",
    sos: "அவசர உதவி", download_map: "ஆஃப்லைன் வரைபடம் பதிவிறக்கு", high_contrast: "அதிக மாறுபாடு",
    rainfall: "மழை", start_set: "தொடக்கம் அமைக்கப்பட்டது — இலக்கைத் தொடவும்",
    outside_network: "தொடுதல் சாலை வலையமைப்புக்கு வெளியே உள்ளது", no_route: "பாதை கிடைக்கவில்லை",
    sos_queued: "அவசர உதவி வரிசையில் (இணையம் வந்ததும் அனுப்பப்படும்)",
    why_route: "இந்த பாதை ஏன்",
  },
  hi: {
    app_title: "रेस्क्यूफ्लो-X",
    safest: "सबसे सुरक्षित मार्ग", fastest: "सबसे तेज़ मार्ग", balanced: "संतुलित",
    sos: "आपातकाल", download_map: "ऑफ़लाइन मानचित्र डाउनलोड करें", high_contrast: "उच्च कंट्रास्ट",
    rainfall: "वर्षा", start_set: "आरंभ सेट — गंतव्य टैप करें",
    outside_network: "टैप सड़क नेटवर्क के बाहर है", no_route: "कोई मार्ग नहीं मिला",
    sos_queued: "SOS कतार में (ऑनलाइन होने पर भेजा जाएगा)",
    why_route: "यह मार्ग क्यों",
  },
};

let current = "en";
export function setLang(lang) { if (MESSAGES[lang]) current = lang; }
export function t(key) { return (MESSAGES[current] && MESSAGES[current][key]) || MESSAGES.en[key] || key; }
export function availableLangs() { return Object.keys(MESSAGES); }
