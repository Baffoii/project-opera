import * as Cesium from 'cesium';
import { paddedBounds, planReveal } from './benchmarkPlan.js';

/**
 * Upstream forbids Cesium labels (world text uses the overlay host), so markers are told apart by colour and
 * the panel carries the legend.
 *
 * Guess pin, reveal markers and geodesic lines for benchmark mode, in one dedicated data source.
 * Globe clicks are captured only while picking is enabled, so upstream click behaviour is untouched otherwise.
 */
export function createBenchmarkOverlays(viewer, { requestRender } = {}) {
  const dataSource = new Cesium.CustomDataSource('opera-benchmark');
  viewer.dataSources.add(dataSource);
  let handler = null;
  let nextId = 0;

  const redraw = () => {
    viewer.scene.requestRender?.();
    requestRender?.('opera-benchmark');
  };

  function addMarker(m) {
    const color = Cesium.Color.fromCssColorString(m.color);
    const small = m.kind === 'context';
    dataSource.entities.add({
      id: `opera-benchmark-${m.kind}-${(nextId += 1)}`,
      name: m.label,
      position: Cesium.Cartesian3.fromDegrees(m.lon, m.lat),
      point: {
        pixelSize: small ? 7 : 13,
        color,
        outlineColor: Cesium.Color.BLACK,
        outlineWidth: 2,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
      },
    });
  }

  function addLine(l) {
    dataSource.entities.add({
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArray([
          l.from.lon,
          l.from.lat,
          l.to.lon,
          l.to.lat,
        ]),
        width: 3,
        arcType: Cesium.ArcType.GEODESIC,
        material: new Cesium.PolylineDashMaterialProperty({
          color: Cesium.Color.fromCssColorString(l.color),
          dashLength: 14,
        }),
      },
    });
  }

  return {
    enablePicking(onPick) {
      this.disablePicking();
      handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
      handler.setInputAction((click) => {
        const cartesian = viewer.camera.pickEllipsoid(
          click.position,
          viewer.scene.globe.ellipsoid,
        );
        if (!cartesian) return;
        const c = Cesium.Cartographic.fromCartesian(cartesian);
        onPick({
          lat: Cesium.Math.toDegrees(c.latitude),
          lon: Cesium.Math.toDegrees(c.longitude),
        });
      }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    },
    disablePicking() {
      handler?.destroy();
      handler = null;
    },
    setGuess(guess) {
      dataSource.entities.removeAll();
      if (guess)
        addMarker({
          kind: 'guess',
          lat: guess.lat,
          lon: guess.lon,
          label: 'Your guess',
          color: '#4cc3ff',
        });
      redraw();
    },
    showReveal(reveal) {
      const plan = planReveal(reveal);
      dataSource.entities.removeAll();
      for (const line of plan.lines) addLine(line);
      for (const marker of plan.markers) addMarker(marker);
      const b = paddedBounds(plan.bounds);
      viewer.camera.flyTo({
        destination: Cesium.Rectangle.fromDegrees(
          b.west,
          b.south,
          b.east,
          b.north,
        ),
        duration: 2,
      });
      redraw();
    },
    clear() {
      dataSource.entities.removeAll();
      redraw();
    },
    destroy() {
      this.disablePicking();
      viewer.dataSources.remove(dataSource, true);
      redraw();
    },
    get entityCount() {
      return dataSource.entities.values.length;
    },
  };
}
