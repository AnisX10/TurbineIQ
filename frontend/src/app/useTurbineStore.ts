import { useContext } from 'react'
import { StoreContext } from './storeContext'

export function useTurbineStore() {
  const store = useContext(StoreContext)
  if (!store) throw new Error('Turbine store is unavailable outside its provider.')
  return store
}
