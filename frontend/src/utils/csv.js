function escapeCsvValue(value) {
  const str = value === null || value === undefined ? '' : String(value)
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export function downloadCsv(filename, rows, columns) {
  const header = columns.map((col) => escapeCsvValue(col.label)).join(',')
  const lines = rows.map((row) => columns.map((col) => escapeCsvValue(row[col.key])).join(','))
  const csvContent = [header, ...lines].join('\r\n')

  const blob = new Blob(['﻿' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
