"""Read Excel cell values without evaluating formulas or executing macros."""
from contextlib import ExitStack
from datetime import date,datetime,time
from pathlib import Path
from itertools import zip_longest
import re
from openpyxl import load_workbook


class ExcelImportError(ValueError):pass


def cell_text(cell):
    value=cell.value
    if value is None:return ''
    if isinstance(value,bool):return 'TRUE' if value else 'FALSE'
    if isinstance(value,(datetime,date,time)):return value.isoformat()
    if isinstance(value,(int,float)):
        # Common identifier format: preserve leading zeroes in e.g. 0000.
        if re.fullmatch(r'0+',cell.number_format or '') and (isinstance(value,int) or value.is_integer()):
            number=int(value);return ('-' if number<0 else '')+str(abs(number)).zfill(len(cell.number_format))
        if isinstance(value,float) and value.is_integer():return str(int(value))
    return str(value)


class ExcelBook:
    def __init__(self,path):
        self.path=Path(path);self._stack=ExitStack()
        try:
            if self.path.suffix.lower()!='.xlsx':
                raise ExcelImportError('Excelの.xlsxファイルを指定してください。.xlsはExcelで.xlsxとして保存してください。')
            self._file=self._stack.enter_context(self.path.open('rb'))
            self.source=load_workbook(self._file,read_only=True,data_only=False,keep_links=False)
            self._stack.callback(self.source.close)
            self.sheets=[sheet.title for sheet in self.source.worksheets]
            if not self.sheets:raise ExcelImportError('読み込めるワークシートがありません。')
        except Exception as error:
            self.close()
            if isinstance(error,ExcelImportError):raise
            raise ExcelImportError(f'Excelを開けません: {error}') from error

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):self._stack.close()

    def read(self,sheet_name):
        try:
            sheet=self.source[sheet_name]
            # Some writers omit or misreport dimensions; use the actual XML rows.
            sheet.reset_dimensions()
            cached=load_workbook(self._file,read_only=True,data_only=True,keep_links=False)
            try:
                values_sheet=cached[sheet_name];values_sheet.reset_dimensions()
                data=[];last_row=last_column=width=0
                for row_number,(source_row,value_row) in enumerate(zip_longest(sheet.iter_rows(),values_sheet.iter_rows()),1):
                    if source_row is None or value_row is None or len(source_row)!=len(value_row):
                        raise ExcelImportError('読み込み中にExcelの内容が変わりました。保存が終わってから読み直してください。')
                    width=max(width,len(source_row))
                    if row_number>10000 or width>256 or row_number*width>200000:
                        raise ExcelImportError('表は10,000行・256列・200,000セル以内にしてください。不要な行・列の書式も削除してください。')
                    result=[]
                    for column,(original,value) in enumerate(zip(source_row,value_row),1):
                        if original.data_type=='f' and value.value is None and value.data_type not in ('s','str','inlineStr'):
                            raise ExcelImportError(f'{sheet_name}!{original.coordinate}: 数式の計算済み値がありません。Excelで再計算して保存してください。')
                        if value.data_type=='e':
                            raise ExcelImportError(f'{sheet_name}!{value.coordinate}: Excelのセルエラー {value.value} を修正してください。')
                        text=cell_text(value);result.append(text)
                        if text!='' or original.data_type in ('f','s','str','inlineStr'):
                            last_row=row_number;last_column=max(last_column,column)
                    data.append(result)
            finally:cached.close()
            if not last_row:raise ExcelImportError('選択したシートに値がありません。')
            # Keep leading/interior empty cells and rows: origin is always A1.
            return [(row+['']*max(0,last_column-len(row)))[:last_column] for row in data[:last_row]]
        except ExcelImportError:raise
        except Exception as error:raise ExcelImportError(f'Excelを読み込めません: {error}') from error
