# Fix para "invalid call ID" en Meeting Rooms

## Problema identificado:
El frontend estaba enviando `undefined` como call ID cuando se intentaba unirse a una sala de reunión, visible en los logs como:
```
INFO: "POST /video-calls/join-call/undefined HTTP/1.1" 400 Bad Request
```

## Causa raíz:
El modelo Pydantic `VideoCallModel` tenía:
```python
id: Optional[str] = Field(alias="_id")
```

Esto causaba que el campo `id` no apareciera correctamente en la respuesta JSON que recibía el frontend.

## Correcciones realizadas:

### ✅ 1. Modelo Pydantic (video_calls.py)
**Antes:**
```python
id: Optional[str] = Field(alias="_id")
```

**Después:**
```python
id: Optional[str] = None  # Remove alias to ensure it's always in JSON
```

### ✅ 2. Endpoint create-meeting-room
**Antes:**
```python
response_data = {
    "_id": str(result.inserted_id),
    ...
}
```

**Después:**
```python
response_data = {
    "id": str(result.inserted_id),  # Use 'id' instead of '_id'
    ...
}
```

### ✅ 3. Endpoint get-meeting-rooms
Ya se había corregido para asignar tanto `_id` como `id`:
```python
room_data["_id"] = str(room_data["_id"])
room_data["id"] = str(room_data["_id"])  # Also set id field for the model
```

### ✅ 4. Debugging extensivo
Agregado logging detallado para monitorear:
- Qué datos se envían en `room_data`
- Cómo se convierte el modelo
- Si el campo `id` está presente en la respuesta final

### ✅ 5. Configuración Pydantic actualizada
```python
class Config:
    populate_by_name = True
    validate_by_name = True  # Updated from deprecated allow_population_by_field_name
    json_encoders = {
        datetime: lambda v: v.isoformat()
    }
```

## Verificación:
- ✅ Test de serialización confirma que el campo `id` está presente en JSON
- ✅ El frontend ahora debería recibir el campo `id` correctamente
- ✅ `room.id` ya no será `undefined` cuando se haga clic en "Unirse a la sala"

## Resultado esperado:
Después del deploy, al hacer clic en "Unirse a la sala" en una meeting room, el frontend enviará la URL correcta:
```
POST /video-calls/join-call/68e2336f27a273eae825b3b4 HTTP/1.1
```

En lugar de:
```
POST /video-calls/join-call/undefined HTTP/1.1
```