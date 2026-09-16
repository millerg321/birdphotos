"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import Map, { Marker, NavigationControl, Popup } from "react-map-gl/maplibre";
import type { StyleSpecification } from "maplibre-gl";
import Supercluster from "supercluster";
import "maplibre-gl/dist/maplibre-gl.css";

export interface MapSighting {
  groupId: string;
  thumbUrl: string;
  speciesLabel: string;
  gpsLat: number;
  gpsLng: number;
}

interface SightingProps {
  sighting: MapSighting;
}

// Plain raster OSM tiles wrapped in a minimal MapLibre style — no API
// key/hosted vector style needed (see plan: Phase 5 — map, and the
// original build plan's tech stack choice of MapLibre specifically for
// this reason).
const OSM_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "&copy; OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

// Centers on the first sighting rather than (0,0) so a personal library
// concentrated in one region (the common case) opens already roughly
// framed, not staring at the middle of the ocean at zoom 1.
function initialViewState(sightings: MapSighting[]) {
  if (sightings.length === 0) {
    return { longitude: 0, latitude: 20, zoom: 1 };
  }
  return { longitude: sightings[0].gpsLng, latitude: sightings[0].gpsLat, zoom: 4 };
}

export function MapView({ sightings }: { sightings: MapSighting[] }) {
  const [viewState, setViewState] = useState(() => initialViewState(sightings));
  const [selected, setSelected] = useState<MapSighting | null>(null);

  // Rebuilt only when the sighting list itself changes, not on every
  // pan/zoom — supercluster's own index is what getClusters queries
  // cheaply per viewState change below.
  const index = useMemo(() => {
    const idx = new Supercluster<SightingProps>({ radius: 50, maxZoom: 16 });
    idx.load(
      sightings.map((s) => ({
        type: "Feature",
        properties: { sighting: s },
        geometry: { type: "Point", coordinates: [s.gpsLng, s.gpsLat] },
      })),
    );
    return idx;
  }, [sightings]);

  // Queried against the whole world rather than the current viewport
  // bounds — simpler (no bounds tracking needed) and plenty fast at a
  // personal-library point count; revisit if this library ever grows
  // into the tens of thousands of sightings.
  const clusters = useMemo(
    () => index.getClusters([-180, -85, 180, 85], Math.floor(viewState.zoom)),
    [index, viewState.zoom],
  );

  return (
    <div className="h-[70vh] w-full overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
      <Map
        {...viewState}
        onMove={(e) => setViewState(e.viewState)}
        mapStyle={OSM_STYLE}
        style={{ width: "100%", height: "100%" }}
      >
        <NavigationControl position="top-right" />
        {clusters.map((feature) => {
          const [lng, lat] = feature.geometry.coordinates;

          if ("cluster" in feature.properties) {
            const clusterId = feature.properties.cluster_id;
            return (
              <Marker key={`cluster-${clusterId}`} longitude={lng} latitude={lat}>
                <button
                  type="button"
                  onClick={() => {
                    const expansionZoom = Math.min(
                      index.getClusterExpansionZoom(clusterId),
                      18,
                    );
                    setViewState((v) => ({ ...v, longitude: lng, latitude: lat, zoom: expansionZoom }));
                  }}
                  className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-blue-600 text-xs font-semibold text-white shadow"
                >
                  {feature.properties.point_count}
                </button>
              </Marker>
            );
          }

          const { sighting } = feature.properties;
          return (
            <Marker
              key={sighting.groupId}
              longitude={lng}
              latitude={lat}
              onClick={(e) => {
                e.originalEvent.stopPropagation();
                setSelected(sighting);
              }}
            >
              <button
                type="button"
                aria-label={sighting.speciesLabel}
                className="h-4 w-4 rounded-full border-2 border-white bg-red-500 shadow"
              />
            </Marker>
          );
        })}
        {selected && (
          <Popup
            longitude={selected.gpsLng}
            latitude={selected.gpsLat}
            onClose={() => setSelected(null)}
            closeOnClick={false}
            anchor="bottom"
          >
            <Link href={`/groups/${selected.groupId}`} className="block w-32">
              {/* eslint-disable-next-line @next/next/no-img-element -- presigned R2 URL */}
              <img
                src={selected.thumbUrl}
                alt={selected.speciesLabel}
                className="h-32 w-32 rounded object-cover"
              />
              <p className="mt-1 text-xs font-medium text-black">{selected.speciesLabel}</p>
            </Link>
          </Popup>
        )}
      </Map>
    </div>
  );
}
