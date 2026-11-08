import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DataChart, distribution } from './Charts'

describe('Graphiques fondés sur les données du moteur', () => {
  it('calcule les fréquences des longueurs de phrases sans données inventées', () => {
    expect(distribution([5, 3, 5, 10])).toEqual([{ name: '3', value: 1 }, { name: '5', value: 2 }, { name: '10', value: 1 }])
    expect(distribution([])).toEqual([])
  })
  it('rend une vraie valeur zéro dans le tableau accessible', () => {
    render(<DataChart title="Score de lisibilité" data={[{ name: 'Score', value: 0 }]} maximum={100}/>)
    expect(screen.getByRole('cell', { name: '0' })).toBeInTheDocument()
    expect(screen.queryByText('Aucune donnée à représenter pour cette analyse.')).not.toBeInTheDocument()
  })
  it('annonce les données absentes sans tracer de valeurs fictives', () => {
    render(<DataChart title="Termes" data={[]}/>)
    expect(screen.getByText('Aucune donnée à représenter pour cette analyse.')).toBeInTheDocument()
  })
})
