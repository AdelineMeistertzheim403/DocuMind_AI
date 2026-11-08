import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { AnalysisResult } from '../types/api'
import { formatNumber } from '../services/api'

export interface ChartDatum { name: string; value: number }
const colors = ['#8B5CF6', '#34E4D4', '#B39AF8', '#6CB6F7']
export function DataChart({ title, subtitle, data, horizontal = false, maximum }: { title: string; subtitle?: string; data: ChartDatum[]; horizontal?: boolean; maximum?: number }) {
  const hasData = data.length > 0
  return <section className="panel chart-panel"><div className="panel-title"><div><h3>{title}</h3>{subtitle && <p>{subtitle}</p>}</div><span className="tiny-dot"/></div>
    {hasData ? <><div className="chart-canvas" role="img" aria-label={`${title}. Données détaillées disponibles ci-dessous.`}>
      <ResponsiveContainer width="100%" height={230} minWidth={0}>
        <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 10, right: 15, left: horizontal ? 12 : -20, bottom: 5 }} accessibilityLayer>
          <CartesianGrid stroke="#26314a" vertical={false} horizontal={!horizontal}/>
          <XAxis type={horizontal ? 'number' : 'category'} dataKey={horizontal ? undefined : 'name'} stroke="#8b98b1" axisLine={false} tickLine={false} fontSize={11} allowDecimals={false}/>
          <YAxis type={horizontal ? 'category' : 'number'} dataKey={horizontal ? 'name' : undefined} domain={maximum && !horizontal ? [0, maximum] : undefined} stroke="#8b98b1" width={horizontal ? 110 : 45} axisLine={false} tickLine={false} fontSize={11} allowDecimals={false}/>
          <Tooltip contentStyle={{ background: '#151F35', border: '1px solid #36415c', borderRadius: 10, color: '#F5F7FF' }} cursor={{ fill: '#ffffff06' }} formatter={value => [formatNumber(Number(value)), 'Valeur']}/>
          <Bar dataKey="value" name="Valeur" radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={horizontal ? 16 : 36} isAnimationActive={false}>
            {data.map((item, index) => <Cell key={item.name} fill={colors[index % colors.length]}/>)}</Bar>
        </BarChart>
      </ResponsiveContainer>
    </div><details className="chart-data"><summary>Voir les valeurs</summary><table><thead><tr><th>Indicateur</th><th>Valeur</th></tr></thead><tbody>{data.map(item => <tr key={item.name}><td>{item.name}</td><td>{formatNumber(item.value)}</td></tr>)}</tbody></table></details></> : <p className="chart-empty">Aucune donnée à représenter pour cette analyse.</p>}
  </section>
}

export function distribution(lengths: number[]): ChartDatum[] {
  const counts = new Map<number, number>()
  for (const value of lengths) counts.set(value, (counts.get(value) || 0) + 1)
  return [...counts.entries()].sort(([a], [b]) => a - b).map(([name, value]) => ({ name: String(name), value }))
}
export const fromRecord = (record: Record<string, number>): ChartDatum[] => Object.entries(record).map(([name, value]) => ({ name, value }))

export function AnalysisCharts({ result }: { result: AnalysisResult }) {
  return <div className="charts-grid">
    <DataChart title="Longueur des phrases" subtitle="Nombre de phrases par longueur, en mots" data={distribution(result.longueurs_phrases)}/>
    <DataChart title="Répartition des phrases" subtitle="Catégories calculées par le moteur" data={fromRecord(result.repartition_longueurs)}/>
    <DataChart title="Mots fréquents" subtitle="Occurrences hors mots courants ignorés" data={result.mots_frequents.map(([name, value]) => ({ name, value }))} horizontal/>
    <DataChart title="Termes techniques" subtitle="Occurrences des termes recherchés" data={result.termes_techniques.map(item => ({ name: item.terme, value: item.occurrences }))} horizontal/>
    <DataChart title="Score de lisibilité" subtitle={`${result.lisibilite.niveau} · score sur 100`} data={[{ name: 'Lisibilité / 100', value: result.lisibilite.score }]} maximum={100}/>
    <DataChart title="Alertes de complexité" subtitle="Signaux repérés dans les phrases longues" data={fromRecord(result.alertes_complexite)} horizontal/>
  </div>
}
