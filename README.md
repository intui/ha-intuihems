
# intuiHEMS - Smart Battery Optimizer

English below

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/intui/intuiHEMS.svg)](https://github.com/intui/ha-intuihems/releases/)

> **Spare Stromkosten & reduziere CO₂** - Dein Batteriespeicher wird automatisch zum optimalen Zeitpunkt gesteuert.

**intuiHEMS** ist ein Smart Battery Optimizer für Home Assistant. Es optimiert deinen Heimspeicher anhand dynamischer Strompreise, Solarprognosen und deines Verbrauchs vollautomatisch.

## ✨ Das sind die Vorteile

- **💰 Kosten senken:** Die Batterie wird bei günstigen Strompreisen geladen und versorgt dein Zuhause bei hohen Preisen aus dem Speicher.

- **🌱 Mehr erneuerbare Energie nutzen:** Die Batterie lädt bevorzugt, wenn viel grüner Strom verfügbar ist.

- **⚡ Netz entlasten:** Lastspitzen werden vermieden, indem teurer und netzbelastender Strom nicht genutzt wird.

- **🤖 Kostenlos & ohne Aufwand:** intuiHEMS ist kostenlos downloadbar und plant den Betrieb deines Speichers vollständig automatisch.

## 🧠 Wie intuiHEMS deinen Speicher optimiert

intuiHEMS erkennt deinen Batteriespeicher, deine PV-Anlage und den Hausverbrauch automatisch, ganz ohne aufwendige Einrichtung.

Mithilfe KI-gestützter Prognosen berechnet das System bis zu 24 Stunden im Voraus, wie sich Stromverbrauch, Solarertrag und Strompreise entwickeln. Auf dieser Basis wird alle 15 Minuten ein optimaler Lade- und Entladeplan erstellt.

So wird dein Speicher genau dann geladen oder genutzt, wenn es wirtschaftlich und ökologisch sinnvoll ist. In deinem Home-Assistant-Dashboard siehst du jederzeit, wie viel Geld und CO₂ du dadurch einsparst.

**Deine Daten bleiben dabei vollständig in deiner Kontrolle und werden nicht an Dritte weitergegeben.**

## ⚠️ Alpha-Version

intuiHEMS befindet sich aktuell in der Alpha-Phase. Die Kernfunktionen sind stabil, dennoch können vereinzelt Bugs auftreten.

Während der Alpha-Phase ist das Plugin kostenlos und auf **100 Tester limitiert**. Feedback aus der Community spielt dabei eine zentrale Rolle. Wenn Ihr dabei sein wollt, schreibt eine kurze Nachricht in das [Diskussionsforum](https://github.com/intui/ha-intuihems/discussions/categories/devices) mit der Beschreibung eures Systems: welche Batterie, Wechselrichter, dyn. Stromtarif.

## 📋 Voraussetzungen

intuiHEMS funktioniert, wenn folgende Punkte erfüllt sind:

- Home Assistant (Version 2024.4 oder neuer)
- Batteriespeicher mit bestehender Home-Assistant-Integration
- Energy Dashboard ist eingerichtet
- Internetverbindung für Prognosen & Optimierung

## 🚀 Installation

### 1. Über HACS installieren
HACS → Integrationen → „intuiHEMS" suchen → Installieren

### 2. Integration hinzufügen
Einstellungen → Geräte & Dienste → intuiHEMS

### 3. Fertig ✨
Dein Batteriespeicher wird jetzt automatisch optimiert.

---

**Hinweis:** Systeme die nicht automatisch erkannt werden, können manuell angebunden werden.

**Mit ❤️ für die Home Assistant Community**


# intuiHEMS - Smart Battery Optimizer

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/intui/intuiHEMS.svg)](https://github.com/intui/intuiHEMS/releases)

> **Save money. Save the planet.** Automatically optimize your home battery to use cheap renewable energy and reduce grid strain.

## 🌍 Why intuiHEMS?

Climate change demands smarter energy use. intuiHEMS helps you:

- **💰 Save money** - Charge when electricity is cheap, use when it's expensive
- **🌱 Use renewable energy** - Maximize solar self-consumption, charge from grid when renewables are abundant
- **⚡ Support the grid** - Reduce peak demand, enable virtual power plants
- **🤖 Zero effort** - AI does the thinking, you save automatically

## ✨ Key Features

- **Zero-config setup** - Auto-detects your battery, solar panels, and house load
- **Smart device learning** - Knows how to control FoxESS, Solis, Huawei, SolarEdge, Growatt (and learns new ones!)
- **AI-powered** - Forecasts your consumption, solar production, and electricity prices
- **Free alpha** - No cost during testing phase
- **Privacy-first** - Your data stays yours

## 🚀 Quick Start

1. **Install via HACS**
   - HACS → Integrations → Explore & Download Repositories
   - Search "intuiHEMS"
   - Install & Restart

2. **Add Integration**
   - Settings → Devices & Services → Add Integration
   - Search "intuiHEMS"
   - Click through setup - we auto-detect everything!

3. **Done!** ✨
   - Your battery is now optimized 24/7
   - Check savings in your dashboard

## 📋 Requirements

- Home Assistant 2024.4.0+
- Home battery system (any brand with HA integration)
- Energy Dashboard configured
- Internet connection

## 🎯 What Gets Optimized?

**Before intuiHEMS:**
- Battery charges randomly
- You buy expensive peak electricity
- Excess solar is wasted or sold cheap

**With intuiHEMS:**
- Battery charges when electricity is cheap (or solar surplus)
- Battery powers your home during expensive hours
- Solar is used optimally
- **Result: 20-40% lower electricity bills** 💰

## 🧠 How It Works

1. **Every 15 minutes**: Reads your battery level, house consumption, solar production
2. **AI forecasts**: Predicts next 24 hours of consumption, solar, and prices
3. **Optimization**: Calculates the perfect battery schedule
4. **Execution**: Tells your battery when to charge/discharge

All the heavy AI computation happens in the cloud - works on any Home Assistant device!

## 🎬 Supported Devices

**Auto-detected (zero config):**
- FoxESS (H1, H3 series)
- Solis
- Huawei
- SolarEdge  
- Growatt

**Learning system:**
- Don't see your brand? No problem!
- Configure it once manually
- We learn and help future users automatically

## ⚠️ Alpha Status

**Current Version:** 2025.11.9.1

This is an **alpha release**. What this means:
- ✅ Core features work great
- ✅ Actively developed and improved
- ⚠️ Free during alpha (normally €5/month planned)
- ⚠️ May have bugs - please report!
- 📊 Limited to 100 alpha testers

**Your feedback shapes the product!**

## 📊 What You Get

- **Daily savings estimate** - See how much you're saving
- **Next action explanation** - Understand what your battery will do and why
- **Optimization control** - Enable/disable anytime
- **Forecasts** - See predicted consumption, solar, and prices

## Alpha Testing Program

### What to Expect

**Status:** Alpha (v0.1.0)
- ✅ Core functionality working
- ✅ Automated registration and setup
- ⚠️ Limited to 100 alpha testers
- ⚠️ May have bugs - please report!

### How to Report Issues

1. Check existing [GitHub Issues](https://github.com/intui/intuiHEMS/issues)
2. Create new issue with:
   - Home Assistant version
   - Integration version
   - Battery/inverter model
   - Detailed description of problem
   - Relevant logs from `Settings → System → Logs`

### Alpha User Limit

The cloud service currently supports **100 alpha users**. To check availability:

```bash
curl https://api.intuihems.io/api/v1/auth/status
```

Response:
```json
{
  "status": "accepting_users",
  "current_users": 45,
  "max_users": 100,
  "alpha_phase": true
}
```

## Privacy & GDPR

### Data Collection

intuiHEMS collects:
- Battery state of charge (every 15 minutes)
- House energy consumption
- Solar power production
- Battery control actions executed
- Electricity prices (from Tibber or EPEX Spot)

### Data Usage

Your data is used for:
- MPC optimization (battery charge/discharge planning)
- ML forecasting (consumption and solar prediction)
- Historical analytics and savings calculation

### Your Rights (GDPR)

| Right | How to Exercise |
|-------|-----------------|
| **Access** (Article 15) | Settings → intuiHEMS → Export Data |
| **Rectification** (Article 16) | Settings → intuiHEMS → Update Configuration |
| **Erasure** (Article 17) | Settings → intuiHEMS → Delete Account |
| **Data Portability** (Article 20) | Settings → intuiHEMS → Export Data (JSON) |

Data is **never shared** with third parties. Data retention: 30 days (configurable).

### Privacy Policy

Full privacy policy: https://api.intuihems.io/api/v1/gdpr/privacy

## 🆘 Need Help?

- 💬 [Discussions](https://github.com/intui/intuiHEMS/discussions) - Ask questions
- 🐛 [Issues](https://github.com/intui/intuiHEMS/issues) - Report bugs
- 📖 [Documentation](https://github.com/intui/intuiHEMS) - Full guides

## Technical Details

### Architecture

- **Cloud Service:** FastAPI (Python), TimescaleDB, Docker
- **MPC Solver:** CVXPY with OSQP backend
- **Forecasting:** Scikit-learn (historical average + weather-enhanced hybrid)
- **Pricing:** Tibber API or ENTSO-E EPEX Spot
- **Communication:** HTTPS REST API (pull-based control)

### Update Frequency

| Task | Frequency |
|------|-----------|
| Sensor data upload | Every 15 minutes |
| Price fetching | Every hour |
| Consumption/solar forecasts | Every 2 hours |
| MPC optimization | Every 15 minutes |
| Control plan fetch | Daily at 00:05 |
| Control execution | :00, :15, :30, :45 minutes |

### Data Storage

- **Local:** Configuration only (API key, entity IDs)
- **Cloud:** Sensor readings (30 days), forecasts, MPC results

## Development

### Local Development

```bash
# Clone repository
git clone https://github.com/intui/intuiHEMS.git
cd intuiHEMS

# Create development environment
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Run tests
pytest tests/
```

### Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create feature branch
3. Add tests
4. Submit pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Roadmap

### v0.2.0 (Beta)
- [ ] Increased user limit (1,000 users)
- [ ] Advanced ML forecasting (weather integration)
- [ ] Multi-battery support
- [ ] Email notifications

### v1.0.0 (Stable)
- [ ] Local compute mode (optional offline operation)
- [ ] Fleet optimization (cross-user insights)
- [ ] Mobile app
- [ ] Subscription plans

### v2.0.0 (Future)
- [ ] Energy community trading
- [ ] Vehicle-to-Grid (V2G) support
- [ ] Commercial deployment features

## Support the Project

intuiHEMS is **free during alpha testing**. If it saves you money, please consider donating to support development:

- [GitHub Sponsors](https://github.com/sponsors/intui)
- Bitcoin: `bc1q...` (coming soon)

**Suggested donation:** 20% of monthly electricity savings

## License

This project is licensed under the BSD-3-Clause License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Based on research by TNO (Netherlands Organization for Applied Scientific Research)
- Built with [Neuromancer](https://github.com/pnnl/neuromancer) framework (PNNL)
- Inspired by Model Predictive Control research in building energy management

## Links

- **Documentation:** https://github.com/intui/intuiHEMS
- **Issues:** https://github.com/intui/intuiHEMS/issues
- **Discussions:** https://github.com/intui/intuiHEMS/discussions
- **Cloud Service:** https://api.intuihems.io
- **Privacy Policy:** https://api.intuihems.io/api/v1/gdpr/privacy

---

**Made with ❤️ for the Home Assistant community**
