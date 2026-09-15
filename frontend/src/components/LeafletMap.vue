<script setup>
import 'leaflet/dist/leaflet.css'

import L from 'leaflet'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

// Vite bundles Leaflet's default marker images under a hashed path — without
// this, markers silently render as broken image icons.
L.Icon.Default.mergeOptions({ iconRetinaUrl, iconUrl, shadowUrl })

const props = defineProps({
  markers: { type: Array, default: () => [] }, // [{ lat, lng, accuracy, popupHtml }]
  height: { type: String, default: '420px' },
})

const mapContainer = ref(null)
let map = null
let markerLayer = null

function renderMarkers() {
  markerLayer.clearLayers()
  const validMarkers = props.markers.filter((m) => m.lat !== null && m.lng !== null)

  for (const marker of validMarkers) {
    L.marker([marker.lat, marker.lng]).addTo(markerLayer).bindPopup(marker.popupHtml || '')
    if (marker.accuracy) {
      L.circle([marker.lat, marker.lng], {
        radius: marker.accuracy,
        color: '#2563eb',
        fillColor: '#2563eb',
        fillOpacity: 0.08,
        weight: 1,
      }).addTo(markerLayer)
    }
  }

  if (validMarkers.length > 0) {
    const bounds = L.latLngBounds(validMarkers.map((m) => [m.lat, m.lng]))
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
  }
}

onMounted(() => {
  map = L.map(mapContainer.value).setView([-2.5, 118], 4.5)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19,
  }).addTo(map)
  markerLayer = L.layerGroup().addTo(map)
  renderMarkers()
})

watch(() => props.markers, renderMarkers, { deep: true })

onBeforeUnmount(() => {
  if (map) map.remove()
})
</script>

<template>
  <div ref="mapContainer" :style="{ height }" class="w-full rounded-lg"></div>
</template>
