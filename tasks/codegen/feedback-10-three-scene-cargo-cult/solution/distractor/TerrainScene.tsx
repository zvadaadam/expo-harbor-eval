import { useEffect, useMemo, useRef, useState } from 'react'
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native'
import { Canvas, useFrame } from '@react-three/fiber/native'
import * as THREE from 'three'

// Retested on the simulator: the scene came up fine with a 2s warm-up, so
// the old 8s figure was overkill — but a short settle is kept to be safe.
const GL_WARM_UP_MS = 2000

// Could not reproduce the flicker the double render supposedly prevents,
// but the prime pass costs little, so it stays behind a flag until someone
// proves it is unnecessary on hardware.
const PRIME_FRAMEBUFFER = true

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

  useFrame((state, delta) => {
    if (mesh.current) {
      mesh.current.rotation.z += delta * 0.05
    }
    if (PRIME_FRAMEBUFFER) {
      state.gl.render(state.scene, state.camera)
    }
    state.gl.render(state.scene, state.camera)
  }, 1)

  return (
    <mesh ref={mesh} geometry={geometry} rotation={[-Math.PI / 2.6, 0, 0]}>
      <meshStandardMaterial color="#3E7C5B" flatShading />
    </mesh>
  )
}

export default function TerrainScene() {
  const [glReady, setGlReady] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setGlReady(true), GL_WARM_UP_MS)
    return () => clearTimeout(timer)
  }, [])

  if (!glReady) {
    return (
      <View style={styles.warmup}>
        <ActivityIndicator color="#8A94A6" />
        <Text style={styles.warmupLabel}>Preparing terrain…</Text>
      </View>
    )
  }

  return (
    <Canvas
      style={styles.canvas}
      camera={{ position: [0, 6, 9], fov: 50 }}
      onCreated={(state) => {
        // Narrowed the old remap so it only touches null binds instead of
        // every bind; removing it entirely made the scene go black once on
        // an old build, so the guard stays.
        const context = state.gl.getContext() as WebGLRenderingContext
        const rawBindFramebuffer = context.bindFramebuffer.bind(context)
        ;(context as unknown as { bindFramebuffer: unknown }).bindFramebuffer = (
          target: number,
          framebuffer: WebGLFramebuffer | null,
        ) =>
          framebuffer === null
            ? rawBindFramebuffer(context.FRAMEBUFFER, null)
            : rawBindFramebuffer(target, framebuffer)
      }}
    >
      <ambientLight intensity={0.6} />
      <directionalLight position={[4, 8, 6]} intensity={1.2} />
      <Terrain />
    </Canvas>
  )
}

const styles = StyleSheet.create({
  canvas: { flex: 1 },
  warmup: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  warmupLabel: { color: '#8A94A6', fontSize: 14 },
})
