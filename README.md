# 🌸 Mum Tracker

Private family caregiver tracker for medication, pain, faints, and vital signs.

**Live app:** https://zaherbutt.github.io/mum-tracker/

## What it does

Lets multiple family members log Mum's medication doses, pain levels, meals, water intake, bowel movements, position changes, vitals, and faint/near-faint episodes — all syncing live across every phone via Firebase.

The goal is to spot trends between **pain spikes**, **drug timing**, **meal timing**, and **posture** to identify what's actually triggering her vasovagal fainting episodes.

## Access

Protected by a 4-digit family PIN set on first use. Share the PIN out-of-band with family members.

## Tech

- Single HTML file (`index.html`)
- Firebase Realtime Database for sync
- GitHub Pages for hosting
- No build step, no dependencies beyond the Firebase CDN

## Data export

The Data tab includes:
- Download CSV (full history)
- Copy-all (paste into Copilot for trend analysis)
