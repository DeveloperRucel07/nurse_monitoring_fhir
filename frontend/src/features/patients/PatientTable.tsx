import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Patient } from "../../entities/clinical/model";
import { usePatientContext } from "./PatientContext";
import { formatDate, maskIdentifier } from "../../shared/utils/format";

const columnHelper = createColumnHelper<Patient>();

export function PatientTable({ patients }: { patients: Patient[] }) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const { selectPatient, privacyMask } = usePatientContext();
  const navigate = useNavigate();
  const columns = useMemo(
    () => [
      columnHelper.accessor("displayName", {
        header: "Patient/in",
        cell: ({ row, getValue }) => (
          <button className="patient-link" onClick={() => { selectPatient(row.original.id); void navigate("/patient"); }}>
            <span className="avatar" aria-hidden="true">{privacyMask ? "•" : getValue().slice(0, 1).toUpperCase()}</span>
            <span><strong>{privacyMask ? "Name geschützt" : getValue()}</strong><small>ID: {privacyMask ? maskIdentifier(row.original.identifier ?? row.original.id) : row.original.identifier ?? row.original.id}</small></span>
          </button>
        ),
      }),
      columnHelper.accessor("birthDate", { header: "Geburtsdatum", cell: (info) => privacyMask ? "••.••.••••" : formatDate(info.getValue()) }),
      columnHelper.accessor("age", { header: "Alter", cell: (info) => info.getValue() !== undefined ? `${info.getValue()} Jahre` : "Nicht verfügbar" }),
      columnHelper.accessor("gender", { header: "Geschlecht" }),
      columnHelper.display({ id: "station", header: "Station / Zimmer", cell: () => <span className="muted">Nicht verfügbar</span> }),
      columnHelper.display({ id: "risk", header: "Risiko", cell: () => <span className="status-badge neutral">Nicht aggregiert</span> }),
      columnHelper.display({
        id: "open",
        header: "",
        cell: ({ row }) => <button className="icon-button subtle" aria-label={`${privacyMask ? "Patient" : row.original.displayName} öffnen`} onClick={() => { selectPatient(row.original.id); void navigate("/patient"); }}><ChevronRight /></button>,
      }),
    ],
    [navigate, privacyMask, selectPatient],
  );
  const table = useReactTable({
    data: patients,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => {
          const sorted = header.column.getIsSorted();
          return <th key={header.id}><button className="sort-button" disabled={!header.column.getCanSort()} onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}{header.column.getCanSort() ? sorted === "asc" ? <ArrowUp /> : sorted === "desc" ? <ArrowDown /> : <ArrowUpDown /> : null}</button></th>;
        })}</tr>)}</thead>
        <tbody>{table.getRowModel().rows.map((row) => <tr key={row.id}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
