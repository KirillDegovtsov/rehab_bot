def format_rehab_plan_text(exercises_json: dict, nutrition_json: dict) -> str:
    res = []
    
    res.append("🏃 **Упражнения:**")
    ex_data = exercises_json.get('exercises', [])
    if isinstance(ex_data, list):
        for ex in ex_data:
            name = ex.get('name', 'Упражнение')
            desc = ex.get('description', '')
            sets = ex.get('sets', '-')
            reps = ex.get('reps', '-')
            res.append(f"• **{name}**: {desc} (Подходы: {sets}, Повторения: {reps})")
    else:
        res.append(str(ex_data))

    global_sets = exercises_json.get('sets')
    global_reps = exercises_json.get('reps')
    if global_sets and global_reps and global_sets != 'None':
        res.append(f"\n🔄 **Общие подходы:** {global_sets} | **Повторения:** {global_reps}")

    res.append("\n🍎 **Питание:**")
    nutr_data = nutrition_json.get('nutrition', {})
    
    if isinstance(nutr_data, dict):
        if 'description' in nutr_data:
            res.append(f"_{nutr_data.get('description')}_")
        if 'meals' in nutr_data:
            meals_dict = {'breakfast': 'Завтрак', 'snack': 'Перекус', 'lunch': 'Обед', 'dinner': 'Ужин'}
            for meal_key, meal_desc in nutr_data['meals'].items():
                ru_name = meals_dict.get(meal_key, meal_key.capitalize())
                res.append(f"• **{ru_name}**: {meal_desc}")
    else:
        res.append(str(nutr_data))

    return "\n".join(res)