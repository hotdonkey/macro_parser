#!/usr/bin/env python3
# parser > service_layer > services.py

import os
import pandas as pd
from pathlib import Path


# ================================================================
# Чтение / сохранение / проверка
# ================================================================

def make_unique_columns(df):
    """
    Делает названия колонок уникальными.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join([str(p).strip() for p in col if str(p).strip()])
            for col in df.columns
        ]

    used = set()
    new_cols = []

    for i, col in enumerate(df.columns):
        base = str(col).strip()

        if not base or base.lower().startswith("unnamed"):
            base = f"col_{i}"

        if base in used:
            counter = 1
            while f"{base}_{counter}" in used:
                counter += 1
            base = f"{base}_{counter}"

        used.add(base)
        new_cols.append(base)

    df.columns = new_cols
    return df


def _find_date_column(df):
    """
    Ищет колонку с датой по имени.
    Если не находит — возвращает первую колонку.
    """
    date_names = {"date", "дата", "даты"}

    for col in df.columns:
        if str(col).strip().lower() in date_names:
            return col

    # Если не нашли по имени — берём первую колонку
    return df.columns[0]


def _move_date_first(df):
    """
    Перемещает колонку с датой на первую позицию.
    """
    date_col = _find_date_column(df)
    cols_order = [date_col] + [c for c in df.columns if c != date_col]
    return df[cols_order]


def read_db(path, sheet_name=0):
    """
    Читает Excel-файл и приводит колонку с датой к формату datetime.
    Колонка даты ищется по имени, а не берётся вслепую.
    """
    path = Path(path)

    if not path.exists():
        print(f"⚠️ Файл не найден: {path}")
        return pd.DataFrame()

    try:
        df = pd.read_excel(path, sheet_name=sheet_name)
    except ValueError:
        df = pd.read_excel(path, sheet_name=0)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join([str(p).strip() for p in col if str(p).strip()])
            for col in df.columns
        ]

    # Удаляем служебную колонку индекса, если она есть
    if df.columns.size > 0:
        first_col_name = str(df.columns[0]).strip().lower()
        if first_col_name.startswith("unnamed") or first_col_name == "":
            df = df.drop(columns=df.columns[0])

    df = make_unique_columns(df)

    # 🧹 ОЧИСТКА ОТ ДУБЛЕЙ КОЛОНОК (nickel_1, date_1, zink_1 и т.д.)
    cols_to_drop = []
    for col in df.columns:
        col_str = str(col)
        if col_str.endswith("_1") or col_str.endswith("_2"):
            base_col = col_str.rsplit("_", 1)[0]
            if base_col in df.columns:
                cols_to_drop.append(col)

    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    empty_cols = [
        col
        for col in df.columns
        if str(col).startswith("col_") and df[col].isna().all()
    ]

    if empty_cols:
        df = df.drop(columns=empty_cols)
        df = make_unique_columns(df)

    if df.empty or df.columns.size == 0:
        return pd.DataFrame()

    # 🔴 Ищем колонку даты по имени, а не берём первую попавшуюся
    df = _move_date_first(df)
    date_col = df.columns[0]

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    df = df.dropna(subset=[date_col])
    df = df.sort_values(date_col).reset_index(drop=True)

    return df


def save_db(df, path, sheet_name, index=False):
    """
    Сохраняет DataFrame в Excel.
    Колонка с датой всегда ставится на первую позицию.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df = make_unique_columns(df.copy())

    # 🔴 Гарантируем что колонка даты на первом месте
    df = _move_date_first(df)

    with pd.ExcelWriter(
        path,
        date_format="YYYY-MM-DD",
        datetime_format="YYYY-MM-DD",
    ) as writer:
        df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=index,
        )


def prepare_for_append(df, target_date_name, target_columns):
    """
    Готовит строки из одной базы для добавления в другую.
    """
    df = df.copy()

    if df.empty:
        return df

    current_date_col = df.columns[0]

    if current_date_col != target_date_name:
        df = df.rename(
            columns={
                current_date_col: target_date_name,
            }
        )

    df = make_unique_columns(df)

    for col in target_columns:
        if col not in df.columns:
            df[col] = None

    df = df[target_columns]

    return df


def check_df(df_1, df_2):
    """
    Сравнивает две базы по колонке с датой.

    1. Добавляет пропущенные даты из одной базы в другую
    2. Заполняет NaN значениями из парной базы
    3. Удаляет полные дубликаты строк
    4. Сохраняет первое вхождение (более раннюю дату)
    """
    if df_1.empty or df_2.empty:
        return df_1.copy(), df_2.copy()

    df_1, df_2 = make_unique_columns(
        df_1.copy()), make_unique_columns(df_2.copy())

    if df_1.empty or df_2.empty:
        return df_1, df_2

    # Ищем колонку даты по имени
    df_1 = _move_date_first(df_1)
    df_2 = _move_date_first(df_2)

    date_col_1, date_col_2 = df_1.columns[0], df_2.columns[0]

    df_1[date_col_1] = pd.to_datetime(
        df_1[date_col_1], errors="coerce").dt.normalize()
    df_2[date_col_2] = pd.to_datetime(
        df_2[date_col_2], errors="coerce").dt.normalize()

    df_1 = df_1.dropna(subset=[date_col_1]).sort_values(
        date_col_1).reset_index(drop=True)
    df_2 = df_2.dropna(subset=[date_col_2]).sort_values(
        date_col_2).reset_index(drop=True)

    dates_1, dates_2 = set(df_1[date_col_1]), set(df_2[date_col_2])

    missing_in_1 = df_2[~df_2[date_col_2].isin(dates_1)].copy()
    missing_in_2 = df_1[~df_1[date_col_1].isin(dates_2)].copy()

    # Добавляем пропущенные даты
    if not missing_in_1.empty:
        missing_in_1 = prepare_for_append(
            missing_in_1, date_col_1, df_1.columns.tolist())
        df_1_checked = pd.concat([df_1, missing_in_1], ignore_index=True)
    else:
        df_1_checked = df_1.copy()

    if not missing_in_2.empty:
        missing_in_2 = prepare_for_append(
            missing_in_2, date_col_2, df_2.columns.tolist())
        df_2_checked = pd.concat([df_2, missing_in_2], ignore_index=True)
    else:
        df_2_checked = df_2.copy()

    # 🔴 НОВЫЙ ШАГ: Заполняем NaN значениями из парной базы
    df_1_checked = _fill_nan_from_pair(
        df_1_checked, df_2_checked, date_col_1, date_col_2)
    df_2_checked = _fill_nan_from_pair(
        df_2_checked, df_1_checked, date_col_2, date_col_1)

    # Очистка дубликатов
    for d, col in [(df_1_checked, date_col_1), (df_2_checked, date_col_2)]:
        if not d.empty:
            d[col] = pd.to_datetime(d[col], errors="coerce").dt.normalize()
            d.dropna(subset=[col], inplace=True)
            d.sort_values(col, inplace=True)
            d.drop_duplicates(inplace=True)
            d.drop_duplicates(subset=[col], keep="first", inplace=True)
            d.reset_index(drop=True, inplace=True)

    # Гарантируем порядок колонок: дата первая
    df_1_checked = _move_date_first(df_1_checked)
    df_2_checked = _move_date_first(df_2_checked)

    return make_unique_columns(df_1_checked), make_unique_columns(df_2_checked)


def _fill_nan_from_pair(df_target, df_source, date_col_target, date_col_source):
    """
    Заполняет NaN в df_target значениями из df_source для совпадающих дат.

    Например: если в LME есть дата 2026-09-03 с NaN,
    а в Westmetall есть эта же дата с реальными значениями,
    заполняем NaN в LME значениями из Westmetall.
    """
    if df_target.empty or df_source.empty:
        return df_target

    df_target = df_target.copy()
    df_source = df_source.copy()

    # Нормализуем даты
    df_target[date_col_target] = pd.to_datetime(
        df_target[date_col_target], errors="coerce").dt.normalize()
    df_source[date_col_source] = pd.to_datetime(
        df_source[date_col_source], errors="coerce").dt.normalize()

    # Создаём словарь: дата -> строка из source
    source_dict = {}
    for _, row in df_source.iterrows():
        date_val = row[date_col_source]
        if pd.notna(date_val):
            source_dict[date_val] = row

    # Заполняем NaN в target
    for idx, row in df_target.iterrows():
        date_val = row[date_col_target]

        if pd.isna(date_val) or date_val not in source_dict:
            continue

        source_row = source_dict[date_val]

        # Для каждой колонки в target, если значение NaN, берём из source
        for col in df_target.columns:
            if col == date_col_target:
                continue

            # Ищем соответствующую колонку в source (может быть с другим регистром)
            source_col = None
            for src_col in df_source.columns:
                if src_col.lower() == col.lower():
                    source_col = src_col
                    break

            if source_col is None:
                continue

            # Если в target NaN, а в source есть значение — заполняем
            if pd.isna(row[col]) and pd.notna(source_row[source_col]):
                df_target.at[idx, col] = source_row[source_col]

    return df_target


def check_and_save_pair(path_1, path_2, pair_name="", index=False):
    """
    Проверяет пару файлов.
    """
    try:
        df_1 = read_db(path_1, sheet_name=0)
        df_2 = read_db(path_2, sheet_name=0)

        if df_1.empty or df_2.empty:
            print(
                f"⚠️ {pair_name}: одна из баз пустая или не найдена, пропускаем"
            )
            return

        df_1_checked, df_2_checked = check_df(df_1, df_2)

        changed_1 = not df_1.equals(df_1_checked)
        changed_2 = not df_2.equals(df_2_checked)

        if changed_1:
            save_db(df_1_checked, path_1, sheet_name="Sheet1", index=index)

        if changed_2:
            save_db(df_2_checked, path_2, sheet_name="Sheet1", index=index)

        if changed_1 or changed_2:
            print(f"{pair_name}: добавлены пропущенные даты и удалены дубликаты")
        else:
            print(f"{pair_name}: OK")

    except Exception as error:
        print(f"❌ Ошибка проверки {pair_name}: {error}")


def show_db(title, path, sheet_name=0, rows=5, show_head=False):
    """
    Визуальный контроль базы.
    """
    df = read_db(path, sheet_name=sheet_name)

    print(title)

    if df.empty:
        print("⚠️ данных нет")
        return

    display(df.head(rows) if show_head else df.tail(rows))


def db_check():
    """
    Проверка целостности парных баз.
    """
    print("Проверка LME / Westmetall...")
    check_and_save_pair(
        LME_PATH,
        WESTMETALL_PATH,
        pair_name="LME / Westmetall",
        index=False,
    )

    print("Проверка Kitco / LBMA...")
    check_and_save_pair(
        KITCO_PATH,
        LBMA_PATH,
        pair_name="Kitco / LBMA",
        index=False,
    )


# ================================================================
# Конвертация Excel в CSV
# ================================================================

def excel_to_csv_db():
    """
    Конвертирует все Excel файлы в CSV для дальнейшего анализа.
    Обходит все папки с данными.
    """

    def df_to_csv(file_path):
        """
        Конвертирует один Excel файл в CSV.
        """
        try:
            file_path = Path(file_path)
            csv_path = file_path.with_suffix('.csv')

            # 🔴 Читаем БЕЗ index_col=0!
            # Если файл многостраничный — берём первый лист
            try:
                df = pd.read_excel(file_path, sheet_name=0)
            except Exception:
                df = pd.read_excel(file_path)

            # Удаляем служебную колонку индекса, если она есть
            if df.columns.size > 0 and str(df.columns[0]).lower().startswith("unnamed"):
                df = df.drop(columns=df.columns[0])

            # Перемещаем колонку даты на первую позицию
            df = _move_date_first(df)

            df.to_csv(csv_path, sep=",", index=False)
            print(f"✅ {file_path.name} -> {csv_path.name}")

        except Exception as e:
            print(f"❌ Ошибка конвертации {file_path}: {e}")

    def find_all_xlsx_files(base_dir):
        """
        Рекурсивно находит все .xlsx файлы.
        """
        xlsx_files = []
        base_path = Path(base_dir)

        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.endswith(".xlsx"):
                    xlsx_files.append(Path(root) / file)

        return xlsx_files

    base_directory = Path.cwd()

    print("Поиск Excel файлов...")
    xlsx_files = find_all_xlsx_files(base_directory)

    print(f"Найдено {len(xlsx_files)} Excel файлов")
    print("Конвертация в CSV...")

    for file_path in xlsx_files:
        df_to_csv(file_path)

    print("Конвертация завершена!")


__all__ = [
    "make_unique_columns",
    "read_db",
    "save_db",
    "prepare_for_append",
    "check_df",
    "check_and_save_pair",
    "show_db",
    "db_check",
    "excel_to_csv_db",
    "_fill_nan_from_pair",
    "_find_date_column",
    "_move_date_first",
]
