/** Aim at a real marker with GlobeMethods and return its projected position. */
export async function aimAtMarker(page, markerId) {
  return page.evaluate(async id => {
    const root = document.querySelector('#root')
    const fiber = root[Object.keys(root).find(key => key.startsWith('__reactContainer'))]
    function find(node) {
      if (!node) return null
      if (node.type?.name === 'GlobeView') return node
      return find(node.child) || find(node.sibling)
    }
    const component = find(fiber.stateNode?.current ?? fiber)
    const marker = component.memoizedProps.markers.find(item => item.id === id)
    let hook = component.memoizedState
    while (typeof hook?.memoizedState?.current?.scene !== 'function') hook = hook.next
    const globe = hook.memoizedState.current
    globe.controls().autoRotate = false
    globe.controls().enableDamping = false
    globe.pointOfView({ lat: marker.lat + 10, lng: marker.lng + 10, altitude: 1.8 }, 0)
    globe.controls().update()
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    const point = globe.getScreenCoords(marker.lat, marker.lng, .007)
    const rect = document.querySelector('.sim-globe-stage canvas').getBoundingClientRect()
    return { x: rect.x + point.x, y: rect.y + point.y }
  }, markerId)
}

/** Send actual pointer input to the projected icon. */
export async function clickMarker(page, markerId) {
  const position = await aimAtMarker(page, markerId)
  await page.mouse.move(position.x, position.y)
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  await page.mouse.click(position.x, position.y)
}
