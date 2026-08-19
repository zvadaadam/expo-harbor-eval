import { useMemo, useRef } from 'react'
import { StyleSheet } from 'react-native'
import { Canvas, useFrame } from '@react-three/fiber/native'
import * as THREE from 'three'

// All four legacy rituals are retired because the current stack makes each
// one unnecessary:
// - No warm-up timer: expo-gl readiness is event-driven (the native surface
//   fires onContextCreate, and the fiber Canvas already defers the GL view
//   until layout), so the canvas can mount immediately.
// - No manual double render: @react-three/fiber's own frame loop renders the
//   scene once and calls endFrameEXP once per frame; expo-gl presents at
//   most once per vsync, so a second render was pure discarded work.
// - No bindFramebuffer patch: expo-gl natively remaps null/0 binds to the
//   view's real default framebuffer for every target, which is exactly what
//   three's setRenderTarget(null) path needs — the userland remap only
//   corrupted the READ/DRAW targets it forced together.
// - three is unpinned to the current 0.185 line, which is inside
//   @react-three/fiber's supported range on a WebGL2-capable expo-gl.
const TERRAIN_SEGMENTS = 96
const TERRAIN_SIZE = 14

function useTerrainGeometry() {
  return useMemo(() => {
    const geometry = new THREE.PlaneGeometry(
      TERRAIN_SIZE,
      TERRAIN_SIZE,
      TERRAIN_SEGMENTS,
      TERRAIN_SEGMENTS,
    )
    const position = geometry.attributes.position
    for (let i = 0; i < position.count; i += 1) {
      const x = position.getX(i)
      const y = position.getY(i)
      const ridge =
        Math.sin(x * 0.8) * Math.cos(y * 0.6) * 0.9 +
        Math.sin(x * 0.23 + y * 0.31) * 0.5
      position.setZ(i, ridge)
    }
    geometry.computeVertexNormals()
    return geometry
  }, [])
}

function Terrain() {
  const mesh = useRef<THREE.Mesh>(null)

  const geometry = useTerrainGeometry()

  useFrame((_, delta) => {
    if (mesh.current) {
      mesh.current.rotation.z += delta * 0.05
    }
  })

  return (
    <mesh ref={mesh} geometry={geometry} rotation={[-Math.PI / 2.6, 0, 0]}>
      <meshStandardMaterial color="#3E7C5B" flatShading />
    </mesh>
  )
}

export default function TerrainScene() {
  return (
    <Canvas style={styles.canvas} camera={{ position: [0, 6, 9], fov: 50 }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[4, 8, 6]} intensity={1.2} />
      <Terrain />
    </Canvas>
  )
}

const styles = StyleSheet.create({
  canvas: { flex: 1 },
})
