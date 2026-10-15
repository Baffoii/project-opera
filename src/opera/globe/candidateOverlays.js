import * as Cesium from 'cesium';
import { flyToAltitudeM, planOverlays } from './overlayPlan.js';

const markerImages = new Map();

function escapeHtml(text) {
  return String(text).replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[
        c
      ],
  );
}

function markerImage(rank, color, active) {
  const key = `${rank}|${color}|${active}`;
  if (markerImages.has(key)) return markerImages.get(key);
  const size = active ? 52 : 40;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 3, 0, Math.PI * 2);
  ctx.fillStyle = '#0b1620';
  ctx.fill();
  ctx.lineWidth = active ? 5 : 3;
  ctx.strokeStyle = active ? '#ffffff' : color;
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.font = `700 ${active ? 26 : 20}px Inter, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(String(rank), size / 2, size / 2 + 1);
  const url = canvas.toDataURL();
  markerImages.set(key, url);
  return url;
}

/**
 * Numbered markers plus uncertainty circles for candidate locations, held in one
 * dedicated data source so removal never touches upstream layers.
 */
export function createCandidateOverlays(viewer, { requestRender } = {}) {
  const dataSource = new Cesium.CustomDataSource('opera-candidates');
  viewer.dataSources.add(dataSource);
  let plan = [];
  let activeRank = null;
  /** @type {Map<string, object>} attribution text → static Cesium.Credit */
  const credits = new Map();

  function removeCredits() {
    for (const credit of credits.values()) {
      try {
        viewer.creditDisplay?.removeStaticCredit?.(credit);
      } catch {
        /* credit display already torn down */
      }
    }
    credits.clear();
  }

  const redraw = () => {
    viewer.scene.requestRender?.();
    requestRender?.('opera-overlays');
  };

  function rebuild() {
    dataSource.entities.removeAll();
    for (const item of plan) {
      const active = item.rank === activeRank;
      const color = Cesium.Color.fromCssColorString(item.color);
      const position = Cesium.Cartesian3.fromDegrees(item.lon, item.lat);
      dataSource.entities.add({
        id: `opera-candidate-${item.rank}`,
        name: `OPERA candidate ${item.rank}`,
        position,
        billboard: {
          image: markerImage(item.rank, item.color, active),
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scaleByDistance: undefined,
        },
        ellipse:
          item.radiusM == null
            ? undefined
            : {
                semiMajorAxis: item.radiusM,
                semiMinorAxis: item.radiusM,
                material: color.withAlpha(active ? 0.32 : 0.14),
                classificationType: Cesium.ClassificationType.BOTH,
              },
      });
    }
    redraw();
  }

  return {
    setCandidates(candidates) {
      plan = planOverlays(candidates);
      if (!plan.some((p) => p.rank === activeRank)) activeRank = null;
      rebuild();
    },
    setActive(rank) {
      if (rank === activeRank) return;
      activeRank = rank;
      rebuild();
    },
    flyTo(candidate) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(
          candidate.lon,
          candidate.lat,
          flyToAltitudeM(candidate.uncertainty_km),
        ),
        duration: 2.2,
      });
      redraw();
    },
    frameAll() {
      if (!plan.length) return;
      const lons = plan.map((p) => p.lon);
      const lats = plan.map((p) => p.lat);
      const pad = 4;
      viewer.camera.flyTo({
        destination: Cesium.Rectangle.fromDegrees(
          Math.max(Math.min(...lons) - pad, -180),
          Math.max(Math.min(...lats) - pad, -85),
          Math.min(Math.max(...lons) + pad, 180),
          Math.min(Math.max(...lats) + pad, 85),
        ),
        duration: 2.2,
      });
      redraw();
    },
    /** Keep one visible static credit per attribution string; credits not listed are removed. */
    setAttributions(texts) {
      const wanted = new Set((texts ?? []).filter(Boolean));
      for (const [text, credit] of [...credits]) {
        if (wanted.has(text)) continue;
        try {
          viewer.creditDisplay?.removeStaticCredit?.(credit);
        } catch {
          /* credit display already torn down */
        }
        credits.delete(text);
      }
      for (const text of wanted) {
        if (credits.has(text) || !viewer.creditDisplay) continue;
        try {
          const credit = new Cesium.Credit(escapeHtml(text), true);
          viewer.creditDisplay.addStaticCredit(credit);
          credits.set(text, credit);
        } catch {
          /* credit display unavailable */
        }
      }
      redraw();
    },
    clear() {
      plan = [];
      activeRank = null;
      dataSource.entities.removeAll();
      removeCredits();
      redraw();
    },
    destroy() {
      removeCredits();
      viewer.dataSources.remove(dataSource, true);
      redraw();
    },
    get entityCount() {
      return dataSource.entities.values.length;
    },
  };
}
